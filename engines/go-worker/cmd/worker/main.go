package main

import (
	"bufio"
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/netip"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type status struct {
	Service      string   `json:"service"`
	Engine       string   `json:"engine"`
	Version      string   `json:"version"`
	Capabilities []string `json:"capabilities"`
}

type networkTarget struct {
	ID      string `json:"id"`
	Host    string `json:"host"`
	Port    int    `json:"port"`
	Timeout int    `json:"timeout_ms,omitempty"`
}

type networkProbeRequest struct {
	Targets     []networkTarget `json:"targets"`
	Concurrency int             `json:"concurrency,omitempty"`
}

type networkProbeResult struct {
	ID        string  `json:"id"`
	Host      string  `json:"host"`
	Port      int     `json:"port"`
	Reachable bool    `json:"reachable"`
	LatencyMS float64 `json:"latency_ms"`
	Error     string  `json:"error,omitempty"`
}

type networkProbeResponse struct {
	Engine  string               `json:"engine"`
	Checked int                  `json:"checked"`
	Results []networkProbeResult `json:"results"`
}

type topologyProbeRequest struct {
	SourceID    string          `json:"source_id"`
	Targets     []networkTarget `json:"targets"`
	Samples     int             `json:"samples,omitempty"`
	Concurrency int             `json:"concurrency,omitempty"`
}

type topologyProbeResult struct {
	ID                 string  `json:"id"`
	Host               string  `json:"host"`
	Port               int     `json:"port"`
	Attempts            int     `json:"attempts"`
	Successes           int     `json:"successes"`
	Reachable           bool    `json:"reachable"`
	ConnectLossPercent  float64 `json:"connect_loss_percent"`
	LatencyMinMS        float64 `json:"latency_min_ms"`
	LatencyAverageMS    float64 `json:"latency_average_ms"`
	LatencyMaxMS        float64 `json:"latency_max_ms"`
	JitterAverageMS     float64 `json:"jitter_average_ms"`
}

type topologyProbeResponse struct {
	Engine   string                `json:"engine"`
	SourceID string                `json:"source_id"`
	Samples  int                   `json:"samples"`
	Results  []topologyProbeResult `json:"results"`
}

type dnsQuery struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Type      string `json:"type"`
	TimeoutMS int    `json:"timeout_ms,omitempty"`
}

type dnsLookupRequest struct {
	Queries     []dnsQuery `json:"queries"`
	Concurrency int        `json:"concurrency,omitempty"`
}

type dnsLookupResult struct {
	ID     string   `json:"id"`
	Name   string   `json:"name"`
	Type   string   `json:"type"`
	Values []string `json:"values"`
	Error  string   `json:"error,omitempty"`
}

type dnsLookupResponse struct {
	Engine  string            `json:"engine"`
	Checked int               `json:"checked"`
	Results []dnsLookupResult `json:"results"`
}

type mailRenderPlanRequest struct {
    HasHTML         bool `json:"has_html"`
    Characters      int  `json:"characters"`
    Lines           int  `json:"lines"`
    LongestLine     int  `json:"longest_line"`
    TableCount      int  `json:"table_count"`
    LinkCount       int  `json:"link_count"`
    AttachmentCount int  `json:"attachment_count"`
}

type mailRenderPlanResponse struct {
    Engine        string `json:"engine"`
    Layout        string `json:"layout"`
    ReaderWidth   string `json:"reader_width"`
    HorizontalFit string `json:"horizontal_fit"`
    Density       string `json:"density"`
    CollapseQuotes bool  `json:"collapse_quotes"`
}

func planMailRender(request mailRenderPlanRequest) mailRenderPlanResponse {
    layout := "document"
    width := "comfortable"
    fit := "wrap"
    density := "comfortable"
    collapseQuotes := request.Characters > 12000
    if request.TableCount > 0 {
        layout = "transactional"
        width = "wide"
        fit = "scroll_tables"
    } else if !request.HasHTML && (request.LongestLine > 220 || (request.Lines <= 3 && request.Characters > 800)) {
        layout = "longform_plain"
        width = "comfortable"
        fit = "wrap"
    } else if request.Characters < 800 {
        density = "compact"
    } else if request.Characters > 6000 {
        density = "long"
    }
    return mailRenderPlanResponse{
        Engine: "go",
        Layout: layout,
        ReaderWidth: width,
        HorizontalFit: fit,
        Density: density,
        CollapseQuotes: collapseQuotes,
    }
}

type originProbeRequest struct {
	Scheme         string `json:"scheme"`
	Hostname       string `json:"hostname"`
	TargetIP       string `json:"target_ip"`
	Port           int    `json:"port"`
	Path           string `json:"path"`
	ExpectedStatus int    `json:"expected_status"`
	TimeoutMS      int    `json:"timeout_ms"`
}

type originProbeResponse struct {
	Engine                   string  `json:"engine"`
	Healthy                  bool    `json:"healthy"`
	ResolvedIP               string  `json:"resolved_ip"`
	StatusCode               *int    `json:"status_code"`
	LatencyMS                int64   `json:"latency_ms"`
	TLSVersion               *string `json:"tls_version"`
	Cipher                   *string `json:"cipher"`
	CertificateIssuer        *string `json:"certificate_issuer"`
	CertificateNotAfter      *string `json:"certificate_not_after"`
	CertificateDaysRemaining *int    `json:"certificate_days_remaining"`
	Error                    *string `json:"error"`
}

var engineStatus = status{
	Service:      "ithute-go-worker",
	Engine:       "go",
	Version:      "0.4.0",
	Capabilities: []string{"health", "network-concurrency", "tcp-reachability", "network-topology-row", "dns-lookup", "origin-http-tls", "mail-render-plan"},
}

func writeJSON(w http.ResponseWriter, code int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(value)
}

func validateTarget(target networkTarget) error {
	if strings.TrimSpace(target.ID) == "" || len(target.ID) > 128 {
		return errors.New("target id is required and must be at most 128 characters")
	}
	if strings.TrimSpace(target.Host) == "" || len(target.Host) > 253 {
		return errors.New("target host is required and must be at most 253 characters")
	}
	if target.Port < 1 || target.Port > 65535 {
		return errors.New("target port must be between 1 and 65535")
	}
	if target.Timeout != 0 && (target.Timeout < 50 || target.Timeout > 5000) {
		return errors.New("timeout_ms must be between 50 and 5000")
	}
	return nil
}

func probeTCP(ctx context.Context, target networkTarget) networkProbeResult {
	timeout := 1200 * time.Millisecond
	if target.Timeout > 0 {
		timeout = time.Duration(target.Timeout) * time.Millisecond
	}
	started := time.Now()
	dialer := net.Dialer{Timeout: timeout}
	address := net.JoinHostPort(strings.TrimSpace(target.Host), strconv.Itoa(target.Port))
	conn, err := dialer.DialContext(ctx, "tcp", address)
	elapsed := float64(time.Since(started).Microseconds()) / 1000.0
	result := networkProbeResult{
		ID: target.ID, Host: target.Host, Port: target.Port,
		Reachable: err == nil, LatencyMS: elapsed,
	}
	if err != nil {
		result.Error = "unreachable"
		return result
	}
	_ = conn.Close()
	return result
}

func runProbes(ctx context.Context, request networkProbeRequest) (networkProbeResponse, error) {
	if len(request.Targets) == 0 || len(request.Targets) > 64 {
		return networkProbeResponse{}, errors.New("targets must contain between 1 and 64 items")
	}
	for _, target := range request.Targets {
		if err := validateTarget(target); err != nil {
			return networkProbeResponse{}, fmt.Errorf("%s: %w", target.ID, err)
		}
	}
	concurrency := request.Concurrency
	if concurrency <= 0 {
		concurrency = 16
	}
	if concurrency > 32 {
		concurrency = 32
	}

	results := make([]networkProbeResult, len(request.Targets))
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	for index, target := range request.Targets {
		index, target := index, target
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[index] = probeTCP(ctx, target)
		}()
	}
	wg.Wait()
	return networkProbeResponse{Engine: "go", Checked: len(results), Results: results}, nil
}


func probeTopologyTarget(ctx context.Context, target networkTarget, samples int) topologyProbeResult {
	result := topologyProbeResult{
		ID: target.ID,
		Host: target.Host,
		Port: target.Port,
		Attempts: samples,
	}
	latencies := make([]float64, 0, samples)
	for attempt := 0; attempt < samples; attempt++ {
		probe := probeTCP(ctx, target)
		if !probe.Reachable {
			continue
		}
		result.Successes++
		latencies = append(latencies, probe.LatencyMS)
	}
	result.Reachable = result.Successes > 0
	result.ConnectLossPercent = (1.0 - float64(result.Successes)/float64(samples)) * 100.0
	if len(latencies) == 0 {
		return result
	}

	result.LatencyMinMS = latencies[0]
	result.LatencyMaxMS = latencies[0]
	var total float64
	var jitterTotal float64
	for index, latency := range latencies {
		total += latency
		if latency < result.LatencyMinMS {
			result.LatencyMinMS = latency
		}
		if latency > result.LatencyMaxMS {
			result.LatencyMaxMS = latency
		}
		if index > 0 {
			delta := latency - latencies[index-1]
			if delta < 0 {
				delta = -delta
			}
			jitterTotal += delta
		}
	}
	result.LatencyAverageMS = total / float64(len(latencies))
	if len(latencies) > 1 {
		result.JitterAverageMS = jitterTotal / float64(len(latencies)-1)
	}
	return result
}

func runTopologyProbe(ctx context.Context, request topologyProbeRequest) (topologyProbeResponse, error) {
	sourceID := strings.TrimSpace(request.SourceID)
	if sourceID == "" || len(sourceID) > 128 {
		return topologyProbeResponse{}, errors.New("source_id is required and must be at most 128 characters")
	}
	if len(request.Targets) == 0 || len(request.Targets) > 64 {
		return topologyProbeResponse{}, errors.New("targets must contain between 1 and 64 items")
	}
	for _, target := range request.Targets {
		if err := validateTarget(target); err != nil {
			return topologyProbeResponse{}, fmt.Errorf("%s: %w", target.ID, err)
		}
		if target.ID == sourceID {
			return topologyProbeResponse{}, errors.New("source_id must not also appear as a target id")
		}
	}

	samples := request.Samples
	if samples <= 0 {
		samples = 3
	}
	if samples > 10 {
		return topologyProbeResponse{}, errors.New("samples must be between 1 and 10")
	}

	concurrency := request.Concurrency
	if concurrency <= 0 {
		concurrency = 8
	}
	if concurrency > 16 {
		concurrency = 16
	}

	results := make([]topologyProbeResult, len(request.Targets))
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	for index, target := range request.Targets {
		index, target := index, target
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[index] = probeTopologyTarget(ctx, target, samples)
		}()
	}
	wg.Wait()

	return topologyProbeResponse{
		Engine: "go",
		SourceID: sourceID,
		Samples: samples,
		Results: results,
	}, nil
}

func validateDNSQuery(query dnsQuery) error {
	if strings.TrimSpace(query.ID) == "" || len(query.ID) > 128 {
		return errors.New("query id is required and must be at most 128 characters")
	}
	if strings.TrimSpace(query.Name) == "" || len(query.Name) > 253 {
		return errors.New("query name is required and must be at most 253 characters")
	}
	switch strings.ToUpper(strings.TrimSpace(query.Type)) {
	case "A", "AAAA", "CNAME", "MX", "TXT", "NS", "PTR":
	default:
		return errors.New("query type must be A, AAAA, CNAME, MX, TXT, NS or PTR")
	}
	if query.TimeoutMS != 0 && (query.TimeoutMS < 100 || query.TimeoutMS > 5000) {
		return errors.New("timeout_ms must be between 100 and 5000")
	}
	return nil
}

func lookupDNS(ctx context.Context, query dnsQuery) dnsLookupResult {
	name := strings.TrimSpace(query.Name)
	rtype := strings.ToUpper(strings.TrimSpace(query.Type))
	timeout := 2500 * time.Millisecond
	if query.TimeoutMS > 0 {
		timeout = time.Duration(query.TimeoutMS) * time.Millisecond
	}
	lookupCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	result := dnsLookupResult{
		ID: query.ID,
		Name: name,
		Type: rtype,
		Values: []string{},
	}
	resolver := net.DefaultResolver
	var err error

	switch rtype {
	case "A", "AAAA":
		var rows []net.IPAddr
		rows, err = resolver.LookupIPAddr(lookupCtx, name)
		if err == nil {
			for _, row := range rows {
				ip := row.IP
				if rtype == "A" && ip.To4() == nil {
					continue
				}
				if rtype == "AAAA" && ip.To4() != nil {
					continue
				}
				result.Values = append(result.Values, ip.String())
			}
		}
	case "CNAME":
		var value string
		value, err = resolver.LookupCNAME(lookupCtx, name)
		if err == nil && value != "" {
			result.Values = append(result.Values, strings.ToLower(strings.TrimSuffix(value, ".")))
		}
	case "MX":
		var rows []*net.MX
		rows, err = resolver.LookupMX(lookupCtx, name)
		if err == nil {
			for _, row := range rows {
				result.Values = append(result.Values, fmt.Sprintf("%d %s", row.Pref, strings.ToLower(strings.TrimSuffix(row.Host, "."))))
			}
		}
	case "TXT":
		var rows []string
		rows, err = resolver.LookupTXT(lookupCtx, name)
		if err == nil {
			result.Values = append(result.Values, rows...)
		}
	case "NS":
		var rows []*net.NS
		rows, err = resolver.LookupNS(lookupCtx, name)
		if err == nil {
			for _, row := range rows {
				result.Values = append(result.Values, strings.ToLower(strings.TrimSuffix(row.Host, ".")))
			}
		}
	case "PTR":
		var rows []string
		rows, err = resolver.LookupAddr(lookupCtx, name)
		if err == nil {
			for _, row := range rows {
				result.Values = append(result.Values, strings.ToLower(strings.TrimSuffix(row, ".")))
			}
		}
	}

	if err != nil {
		var dnsErr *net.DNSError
		if errors.As(err, &dnsErr) && dnsErr.IsNotFound {
			result.Error = "not_found"
		} else {
			result.Error = "lookup_failed"
		}
	}
	return result
}

func runDNSLookups(ctx context.Context, request dnsLookupRequest) (dnsLookupResponse, error) {
	if len(request.Queries) == 0 || len(request.Queries) > 64 {
		return dnsLookupResponse{}, errors.New("queries must contain between 1 and 64 items")
	}
	for _, query := range request.Queries {
		if err := validateDNSQuery(query); err != nil {
			return dnsLookupResponse{}, fmt.Errorf("%s: %w", query.ID, err)
		}
	}
	concurrency := request.Concurrency
	if concurrency <= 0 {
		concurrency = 16
	}
	if concurrency > 32 {
		concurrency = 32
	}

	results := make([]dnsLookupResult, len(request.Queries))
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	for index, query := range request.Queries {
		index, query := index, query
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[index] = lookupDNS(ctx, query)
		}()
	}
	wg.Wait()
	return dnsLookupResponse{Engine: "go", Checked: len(results), Results: results}, nil
}

var blockedPrefixes = []netip.Prefix{
	netip.MustParsePrefix("0.0.0.0/8"),
	netip.MustParsePrefix("10.0.0.0/8"),
	netip.MustParsePrefix("100.64.0.0/10"),
	netip.MustParsePrefix("127.0.0.0/8"),
	netip.MustParsePrefix("169.254.0.0/16"),
	netip.MustParsePrefix("172.16.0.0/12"),
	netip.MustParsePrefix("192.0.0.0/24"),
	netip.MustParsePrefix("192.0.2.0/24"),
	netip.MustParsePrefix("192.168.0.0/16"),
	netip.MustParsePrefix("198.18.0.0/15"),
	netip.MustParsePrefix("198.51.100.0/24"),
	netip.MustParsePrefix("203.0.113.0/24"),
	netip.MustParsePrefix("224.0.0.0/4"),
	netip.MustParsePrefix("240.0.0.0/4"),
	netip.MustParsePrefix("::/128"),
	netip.MustParsePrefix("::1/128"),
	netip.MustParsePrefix("fc00::/7"),
	netip.MustParsePrefix("fe80::/10"),
	netip.MustParsePrefix("ff00::/8"),
	netip.MustParsePrefix("2001:db8::/32"),
}

func publicTargetIP(value string) (netip.Addr, bool) {
	addr, err := netip.ParseAddr(strings.TrimSpace(value))
	if err != nil {
		return netip.Addr{}, false
	}
	addr = addr.Unmap()
	if !addr.IsValid() || addr.IsUnspecified() || addr.IsLoopback() || addr.IsPrivate() || addr.IsLinkLocalUnicast() || addr.IsLinkLocalMulticast() || addr.IsMulticast() {
		return netip.Addr{}, false
	}
	for _, prefix := range blockedPrefixes {
		if prefix.Contains(addr) {
			return netip.Addr{}, false
		}
	}
	return addr, true
}

func tlsVersionName(version uint16) string {
	switch version {
	case tls.VersionTLS13:
		return "TLSv1.3"
	case tls.VersionTLS12:
		return "TLSv1.2"
	case tls.VersionTLS11:
		return "TLSv1.1"
	case tls.VersionTLS10:
		return "TLSv1.0"
	default:
		return fmt.Sprintf("TLS-%d", version)
	}
}

func intPtr(value int) *int {
	return &value
}

func runOriginProbe(ctx context.Context, request originProbeRequest) (originProbeResponse, error) {
	scheme := strings.ToLower(strings.TrimSpace(request.Scheme))
	if scheme != "http" && scheme != "https" {
		return originProbeResponse{}, errors.New("scheme must be http or https")
	}
	hostname := strings.ToLower(strings.TrimSuffix(strings.TrimSpace(request.Hostname), "."))
	if hostname == "" || len(hostname) > 253 {
		return originProbeResponse{}, errors.New("hostname is invalid")
	}
	addr, ok := publicTargetIP(request.TargetIP)
	if !ok {
		return originProbeResponse{}, errors.New("target_ip must be a globally routable public address")
	}
	if request.Port < 1 || request.Port > 65535 {
		return originProbeResponse{}, errors.New("port is invalid")
	}
	if !strings.HasPrefix(request.Path, "/") || len(request.Path) > 4096 || strings.ContainsAny(request.Path, "\r\n") {
		return originProbeResponse{}, errors.New("path is invalid")
	}
	if request.ExpectedStatus < 100 || request.ExpectedStatus > 599 {
		return originProbeResponse{}, errors.New("expected_status must be between 100 and 599")
	}
	if request.TimeoutMS < 1000 || request.TimeoutMS > 30000 {
		return originProbeResponse{}, errors.New("timeout_ms must be between 1000 and 30000")
	}

	started := time.Now()
	timeout := time.Duration(request.TimeoutMS) * time.Millisecond
	probeCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	dialer := net.Dialer{Timeout: timeout}
	raw, err := dialer.DialContext(probeCtx, "tcp", net.JoinHostPort(addr.String(), strconv.Itoa(request.Port)))
	response := originProbeResponse{
		Engine:     "go",
		ResolvedIP: addr.String(),
		LatencyMS:  0,
	}
	if err != nil {
		message := "connect failed"
		response.Error = &message
		response.LatencyMS = time.Since(started).Milliseconds()
		return response, nil
	}
	defer raw.Close()
	_ = raw.SetDeadline(time.Now().Add(timeout))

	var stream net.Conn = raw
	if scheme == "https" {
		secure := tls.Client(raw, &tls.Config{
			ServerName: hostname,
			MinVersion: tls.VersionTLS12,
		})
		if err := secure.HandshakeContext(probeCtx); err != nil {
			message := "TLS handshake failed"
			response.Error = &message
			response.LatencyMS = time.Since(started).Milliseconds()
			return response, nil
		}
		state := secure.ConnectionState()
		version := tlsVersionName(state.Version)
		cipher := tls.CipherSuiteName(state.CipherSuite)
		response.TLSVersion = &version
		response.Cipher = &cipher
		if len(state.PeerCertificates) > 0 {
			cert := state.PeerCertificates[0]
			issuer := cert.Issuer.String()
			notAfter := cert.NotAfter.UTC().Format(time.RFC3339)
			days := int(time.Until(cert.NotAfter).Hours() / 24)
			response.CertificateIssuer = &issuer
			response.CertificateNotAfter = &notAfter
			response.CertificateDaysRemaining = &days
		}
		stream = secure
	}

	hostHeader := hostname
	defaultPort := 80
	if scheme == "https" {
		defaultPort = 443
	}
	if request.Port != defaultPort {
		hostHeader = net.JoinHostPort(hostname, strconv.Itoa(request.Port))
	}
	requestText := "GET " + request.Path + " HTTP/1.1\r\n" +
		"Host: " + hostHeader + "\r\n" +
		"User-Agent: Ithute-Edge-Health/2.0\r\n" +
		"Accept: */*\r\n" +
		"Connection: close\r\n\r\n"
	if _, err := stream.Write([]byte(requestText)); err != nil {
		message := "request write failed"
		response.Error = &message
		response.LatencyMS = time.Since(started).Milliseconds()
		return response, nil
	}

	reader := bufio.NewReaderSize(stream, 16*1024)
	line, err := reader.ReadString('\n')
	if err != nil && len(line) == 0 {
		message := "origin did not return an HTTP status line"
		response.Error = &message
		response.LatencyMS = time.Since(started).Milliseconds()
		return response, nil
	}
	parts := strings.Fields(strings.TrimSpace(line))
	if len(parts) < 2 || !strings.HasPrefix(parts[0], "HTTP/") {
		message := "origin did not return a valid HTTP status line"
		response.Error = &message
		response.LatencyMS = time.Since(started).Milliseconds()
		return response, nil
	}
	statusCode, err := strconv.Atoi(parts[1])
	if err != nil || statusCode < 100 || statusCode > 599 {
		message := "origin returned an invalid HTTP status"
		response.Error = &message
		response.LatencyMS = time.Since(started).Milliseconds()
		return response, nil
	}
	response.StatusCode = intPtr(statusCode)
	response.Healthy = statusCode == request.ExpectedStatus
	response.LatencyMS = time.Since(started).Milliseconds()
	return response, nil
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})
	mux.HandleFunc("GET /v1/capabilities", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})
	mux.HandleFunc("POST /v1/network/probe", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64*1024))
		decoder.DisallowUnknownFields()
		var request networkProbeRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		response, err := runProbes(r.Context(), request)
		if err != nil {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	})
	mux.HandleFunc("POST /v1/network/topology", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64*1024))
		decoder.DisallowUnknownFields()
		var request topologyProbeRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		response, err := runTopologyProbe(r.Context(), request)
		if err != nil {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	})
	mux.HandleFunc("POST /v1/dns/lookup", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64*1024))
		decoder.DisallowUnknownFields()
		var request dnsLookupRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		response, err := runDNSLookups(r.Context(), request)
		if err != nil {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	})
	mux.HandleFunc("POST /v1/mail/render-plan", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16*1024))
		decoder.DisallowUnknownFields()
		var request mailRenderPlanRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		if request.Characters < 0 || request.Lines < 0 || request.LongestLine < 0 || request.TableCount < 0 || request.LinkCount < 0 || request.AttachmentCount < 0 {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": "render metrics must be non-negative"})
			return
		}
		writeJSON(w, http.StatusOK, planMailRender(request))
	})
	mux.HandleFunc("POST /v1/network/origin", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 32*1024))
		decoder.DisallowUnknownFields()
		var request originProbeRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		response, err := runOriginProbe(r.Context(), request)
		if err != nil {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, response)
	})

	server := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       35 * time.Second,
		WriteTimeout:      35 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	log.Printf("starting %s %s", engineStatus.Service, engineStatus.Version)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("worker stopped: %v", err)
		os.Exit(1)
	}
}
