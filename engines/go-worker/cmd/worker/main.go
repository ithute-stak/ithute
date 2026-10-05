package main

import (
	"bufio"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/tls"
	"encoding/base64"
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

	"github.com/gorilla/websocket"
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

type originProbeRequest struct {
	Scheme         string `json:"scheme"`
	Hostname       string `json:"hostname"`
	TargetIP       string `json:"target_ip"`
	Port           int    `json:"port"`
	Path           string `json:"path"`
	ExpectedStatus int    `json:"expected_status"`
	TimeoutMS      int    `json:"timeout_ms"`
}

type pushDeliveryRequest struct {
    Endpoint     string         `json:"endpoint"`
    DeliveryID   string         `json:"delivery_id,omitempty"`
    TTLSeconds   int            `json:"ttl_seconds"`
    Notification map[string]any `json:"notification"`
}

type pushEnvelope struct {
    MessageID    string         `json:"message_id"`
    DeliveryID   string         `json:"delivery_id,omitempty"`
    ExpiresAt    int64          `json:"expires_at"`
    Notification map[string]any `json:"notification"`
}

type pushDeliveryResponse struct {
    Engine    string `json:"engine"`
    MessageID string `json:"message_id"`
    Queued    bool   `json:"queued"`
}

type pushBroker struct {
    mu      sync.Mutex
    waiters map[string]chan pushEnvelope
    counter uint64
}

func newPushBroker() *pushBroker {
    return &pushBroker{waiters: make(map[string]chan pushEnvelope)}
}

func (b *pushBroker) register(endpoint string) chan pushEnvelope {
    b.mu.Lock()
    defer b.mu.Unlock()
    waiter := make(chan pushEnvelope, 1)
    b.waiters[endpoint] = waiter
    return waiter
}

func (b *pushBroker) unregister(endpoint string, waiter chan pushEnvelope) {
    b.mu.Lock()
    defer b.mu.Unlock()
    if current, ok := b.waiters[endpoint]; ok && current == waiter {
        delete(b.waiters, endpoint)
    }
}

func (b *pushBroker) active(endpoint string) chan pushEnvelope {
    b.mu.Lock()
    defer b.mu.Unlock()
    return b.waiters[endpoint]
}

func (b *pushBroker) nextID() string {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.counter++
    return fmt.Sprintf("ithute-%d-%d", time.Now().UnixMilli(), b.counter)
}

func (b *pushBroker) deliver(request pushDeliveryRequest) (pushDeliveryResponse, error) {
    endpoint := strings.TrimSpace(request.Endpoint)
    if len(endpoint) < 16 || len(endpoint) > 8192 {
        return pushDeliveryResponse{}, errors.New("endpoint must contain 16 to 8192 characters")
    }
    if request.TTLSeconds < 1 || request.TTLSeconds > 604800 {
        return pushDeliveryResponse{}, errors.New("ttl_seconds must be between 1 and 604800")
    }
    if request.Notification == nil {
        return pushDeliveryResponse{}, errors.New("notification is required")
    }
    envelope := pushEnvelope{
        MessageID: b.nextID(),
        DeliveryID: strings.TrimSpace(request.DeliveryID),
        ExpiresAt: time.Now().Add(time.Duration(request.TTLSeconds) * time.Second).Unix(),
        Notification: request.Notification,
    }
    waiter := b.active(endpoint)
    if waiter == nil {
        return pushDeliveryResponse{}, errors.New("endpoint is not actively connected")
    }
    select {
    case waiter <- envelope:
        return pushDeliveryResponse{Engine: "go", MessageID: envelope.MessageID, Queued: true}, nil
    default:
        return pushDeliveryResponse{}, errors.New("endpoint is not ready")
    }
}

func constantTimeTokenMatch(got, expected string) bool {
    if expected == "" || len(got) != len(expected) {
        return false
    }
    var diff byte
    for i := 0; i < len(got); i++ {
        diff |= got[i] ^ expected[i]
    }
    return diff == 0
}

func bearerValue(header string) string {
    const prefix = "Bearer "
    if !strings.HasPrefix(header, prefix) {
        return ""
    }
    return strings.TrimSpace(strings.TrimPrefix(header, prefix))
}

func endpointFromRequest(r *http.Request) string {
    if value := strings.TrimSpace(r.Header.Get("X-Ithute-Push-Endpoint")); value != "" {
        return value
    }
    return strings.TrimSpace(r.URL.Query().Get("endpoint"))
}


type realtimeTicket struct {
	ApplicationID string `json:"application_id"`
	Sub           string `json:"sub"`
	DeviceKey     string `json:"device_key"`
	ExpiresAt     int64  `json:"exp"`
}

type realtimePublishRequest struct {
	ApplicationID      string         `json:"application_id"`
	Recipients         []string       `json:"recipients"`
	BroadcastConnected bool           `json:"broadcast_connected"`
	Event              map[string]any `json:"event"`
}

type realtimeConnection struct {
	id        string
	appID     string
	sub       string
	deviceKey string
	conn      *websocket.Conn
	writeMu   sync.Mutex
}

type realtimeBroker struct {
	mu          sync.RWMutex
	connections map[string]map[string]*realtimeConnection
	counter     uint64
}

func newRealtimeBroker() *realtimeBroker {
	return &realtimeBroker{connections: make(map[string]map[string]*realtimeConnection)}
}

func realtimeKey(appID, sub string) string {
	return appID + "\x00" + sub
}

func (b *realtimeBroker) nextID() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.counter++
	return fmt.Sprintf("rt-%d-%d", time.Now().UnixMilli(), b.counter)
}

func (b *realtimeBroker) register(ticket realtimeTicket, conn *websocket.Conn) *realtimeConnection {
	record := &realtimeConnection{
		id: b.nextID(), appID: ticket.ApplicationID, sub: ticket.Sub,
		deviceKey: ticket.DeviceKey, conn: conn,
	}
	key := realtimeKey(ticket.ApplicationID, ticket.Sub)
	b.mu.Lock()
	defer b.mu.Unlock()
	bucket := b.connections[key]
	if bucket == nil {
		bucket = make(map[string]*realtimeConnection)
		b.connections[key] = bucket
	}
	bucket[record.id] = record
	return record
}

func (b *realtimeBroker) unregister(record *realtimeConnection) {
	key := realtimeKey(record.appID, record.sub)
	b.mu.Lock()
	defer b.mu.Unlock()
	if bucket := b.connections[key]; bucket != nil {
		delete(bucket, record.id)
		if len(bucket) == 0 {
			delete(b.connections, key)
		}
	}
}

func (b *realtimeBroker) presence(appID, sub string) int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.connections[realtimeKey(appID, sub)])
}

func (b *realtimeBroker) snapshot(request realtimePublishRequest) []*realtimeConnection {
	b.mu.RLock()
	defer b.mu.RUnlock()
	result := make([]*realtimeConnection, 0)
	if request.BroadcastConnected {
		prefix := request.ApplicationID + "\x00"
		for key, bucket := range b.connections {
			if strings.HasPrefix(key, prefix) {
				for _, record := range bucket {
					result = append(result, record)
				}
			}
		}
		return result
	}
	seen := make(map[string]struct{})
	for _, sub := range request.Recipients {
		if _, ok := seen[sub]; ok {
			continue
		}
		seen[sub] = struct{}{}
		for _, record := range b.connections[realtimeKey(request.ApplicationID, sub)] {
			result = append(result, record)
		}
	}
	return result
}

func (b *realtimeBroker) publish(request realtimePublishRequest) int {
	payload, err := json.Marshal(request.Event)
	if err != nil {
		return 0
	}
	delivered := 0
	for _, record := range b.snapshot(request) {
		record.writeMu.Lock()
		err := record.conn.WriteMessage(websocket.TextMessage, payload)
		record.writeMu.Unlock()
		if err == nil {
			delivered++
		}
	}
	return delivered
}

func verifyRealtimeTicket(raw, secret string) (realtimeTicket, error) {
	var ticket realtimeTicket
	parts := strings.Split(raw, ".")
	if len(parts) != 2 || secret == "" {
		return ticket, errors.New("invalid ticket")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return ticket, errors.New("invalid ticket")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return ticket, errors.New("invalid ticket")
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(payload)
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return ticket, errors.New("invalid ticket")
	}
	if err := json.Unmarshal(payload, &ticket); err != nil {
		return ticket, errors.New("invalid ticket")
	}
	if ticket.ExpiresAt < time.Now().Unix() || ticket.ExpiresAt > time.Now().Add(2*time.Minute).Unix() {
		return ticket, errors.New("expired ticket")
	}
	if ticket.ApplicationID == "" || ticket.Sub == "" || len(ticket.DeviceKey) < 8 || len(ticket.DeviceKey) > 200 {
		return ticket, errors.New("invalid ticket")
	}
	return ticket, nil
}

var websocketUpgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	CheckOrigin: func(r *http.Request) bool {
		origin := strings.TrimSpace(r.Header.Get("Origin"))
		return origin == "" || strings.HasSuffix(origin, ".ithute.co.ls") || origin == "https://ithute.co.ls"
	},
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
	Version:      "0.5.0",
	Capabilities: []string{"health", "network-concurrency", "tcp-reachability", "dns-lookup", "origin-http-tls", "push-delivery", "push-long-poll", "realtime-websocket", "realtime-fanout", "realtime-presence"},
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

func stringPtr(value string) *string {
	return &value
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
	broker := newPushBroker()
	realtime := newRealtimeBroker()
	gatewayToken := strings.TrimSpace(os.Getenv("ITHUTE_PUSH_GATEWAY_TOKEN"))
	realtimeToken := strings.TrimSpace(os.Getenv("ITHUTE_REALTIME_GATEWAY_TOKEN"))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})
	mux.HandleFunc("GET /v1/capabilities", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})
	mux.HandleFunc("GET /v1/realtime/ws", func(w http.ResponseWriter, r *http.Request) {
		ticket, err := verifyRealtimeTicket(strings.TrimSpace(r.URL.Query().Get("ticket")), realtimeToken)
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid_ticket"})
			return
		}
		conn, err := websocketUpgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		record := realtime.register(ticket, conn)
		defer realtime.unregister(record)
		_ = conn.SetReadDeadline(time.Now().Add(75 * time.Second))
		conn.SetPongHandler(func(string) error {
			return conn.SetReadDeadline(time.Now().Add(75 * time.Second))
		})
		record.writeMu.Lock()
		_ = conn.WriteJSON(map[string]any{
			"type": "ready", "version": 3, "engine": "go",
			"application_id": ticket.ApplicationID, "sub": ticket.Sub,
			"connection_id": record.id, "heartbeat_seconds": 30,
		})
		record.writeMu.Unlock()
		for {
			messageType, payload, err := conn.ReadMessage()
			if err != nil {
				return
			}
			if messageType != websocket.TextMessage || len(payload) > 64*1024 {
				_ = conn.WriteControl(websocket.CloseMessage, websocket.FormatCloseMessage(4400, "invalid frame"), time.Now().Add(time.Second))
				return
			}
			var frame map[string]any
			if json.Unmarshal(payload, &frame) != nil {
				continue
			}
			if frame["type"] == "ping" {
				_ = conn.SetReadDeadline(time.Now().Add(75 * time.Second))
				record.writeMu.Lock()
				_ = conn.WriteJSON(map[string]any{"type": "pong", "connection_id": record.id})
				record.writeMu.Unlock()
			}
		}
	})
	mux.HandleFunc("POST /v1/realtime/publish", func(w http.ResponseWriter, r *http.Request) {
		if !constantTimeTokenMatch(bearerValue(r.Header.Get("Authorization")), realtimeToken) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 128*1024))
		decoder.DisallowUnknownFields()
		var request realtimePublishRequest
		if err := decoder.Decode(&request); err != nil || strings.TrimSpace(request.ApplicationID) == "" || request.Event == nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		delivered := realtime.publish(request)
		writeJSON(w, http.StatusOK, map[string]any{"engine": "go", "delivered": delivered})
	})
	mux.HandleFunc("GET /v1/realtime/presence", func(w http.ResponseWriter, r *http.Request) {
		if !constantTimeTokenMatch(bearerValue(r.Header.Get("Authorization")), realtimeToken) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		appID := strings.TrimSpace(r.URL.Query().Get("application_id"))
		sub := strings.TrimSpace(r.URL.Query().Get("sub"))
		if appID == "" || sub == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "application_id and sub are required"})
			return
		}
		count := realtime.presence(appID, sub)
		writeJSON(w, http.StatusOK, map[string]any{"engine": "go", "online": count > 0, "connection_count": count})
	})
	mux.HandleFunc("POST /v1/push/deliver", func(w http.ResponseWriter, r *http.Request) {
		if !constantTimeTokenMatch(bearerValue(r.Header.Get("Authorization")), gatewayToken) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		defer r.Body.Close()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16*1024))
		decoder.DisallowUnknownFields()
		var request pushDeliveryRequest
		if err := decoder.Decode(&request); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		response, err := broker.deliver(request)
		if err != nil {
			status := http.StatusUnprocessableEntity
			if err.Error() == "endpoint is not actively connected" || err.Error() == "endpoint is not ready" {
				status = http.StatusServiceUnavailable
			}
			writeJSON(w, status, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusAccepted, response)
	})
	mux.HandleFunc("GET /v1/push/poll", func(w http.ResponseWriter, r *http.Request) {
		endpoint := endpointFromRequest(r)
		if len(endpoint) < 16 || len(endpoint) > 8192 {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid endpoint"})
			return
		}
		timeout := 25 * time.Second
		if value := strings.TrimSpace(r.URL.Query().Get("timeout_seconds")); value != "" {
			seconds, err := strconv.Atoi(value)
			if err != nil || seconds < 1 || seconds > 30 {
				writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": "timeout_seconds must be between 1 and 30"})
				return
			}
			timeout = time.Duration(seconds) * time.Second
		}
		timer := time.NewTimer(timeout)
		defer timer.Stop()
		waiter := broker.register(endpoint)
		defer broker.unregister(endpoint, waiter)
		for {
			select {
			case <-r.Context().Done():
				return
			case <-timer.C:
				w.WriteHeader(http.StatusNoContent)
				return
			case message := <-waiter:
				if message.ExpiresAt <= time.Now().Unix() {
					continue
				}
				writeJSON(w, http.StatusOK, message)
				return
			}
		}
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
