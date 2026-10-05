package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const version = "ithute-db-gateway/1"

type route struct {
	EndpointID string `json:"endpoint_id"`
	Hostname string `json:"hostname"`
	ListenPort int `json:"listen_port"`
	TargetHost string `json:"target_host"`
	TargetPort int `json:"target_port"`
	Generation int64 `json:"generation"`
}
type snapshot struct {
	GatewayID string `json:"gateway_id"`
	Routes []route `json:"routes"`
}
type ackPayload struct { Generation int64 `json:"generation"` }
type heartbeatPayload struct { Version string `json:"version"` }

type config struct {
	APIURL string
	Token string
	BindIP string
	PollInterval time.Duration
	DialTimeout time.Duration
	AllowHTTP bool
}

func loadConfig() (config, error) {
	cfg := config{
		APIURL: strings.TrimRight(strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_API_URL")), "/"),
		Token: strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_TOKEN")),
		BindIP: strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_BIND_IP")),
		PollInterval: 5 * time.Second,
		DialTimeout: 5 * time.Second,
		AllowHTTP: strings.EqualFold(strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_ALLOW_HTTP")), "true"),
	}
	if cfg.BindIP == "" { cfg.BindIP = "0.0.0.0" }
	if value := strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_POLL_SECONDS")); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil || n < 2 || n > 60 { return config{}, errors.New("ITHUTE_DB_GATEWAY_POLL_SECONDS must be between 2 and 60") }
		cfg.PollInterval = time.Duration(n) * time.Second
	}
	if value := strings.TrimSpace(os.Getenv("ITHUTE_DB_GATEWAY_DIAL_TIMEOUT_SECONDS")); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil || n < 1 || n > 30 { return config{}, errors.New("ITHUTE_DB_GATEWAY_DIAL_TIMEOUT_SECONDS must be between 1 and 30") }
		cfg.DialTimeout = time.Duration(n) * time.Second
	}
	if cfg.APIURL == "" { return config{}, errors.New("ITHUTE_DB_GATEWAY_API_URL is required") }
	parsed, err := url.Parse(cfg.APIURL)
	if err != nil || parsed.Host == "" { return config{}, errors.New("ITHUTE_DB_GATEWAY_API_URL is invalid") }
	if parsed.Scheme != "https" && !(cfg.AllowHTTP && parsed.Scheme == "http") {
		return config{}, errors.New("database gateway control-plane URL must use HTTPS")
	}
	if !strings.HasPrefix(cfg.Token, "ith_dbgw_") || len(cfg.Token) < 30 {
		return config{}, errors.New("ITHUTE_DB_GATEWAY_TOKEN is invalid")
	}
	if net.ParseIP(cfg.BindIP) == nil { return config{}, errors.New("ITHUTE_DB_GATEWAY_BIND_IP must be an IP address") }
	return cfg, nil
}

type apiClient struct {
	baseURL string
	token string
	client *http.Client
}

func (a *apiClient) request(ctx context.Context, method, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil { return err }
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, a.baseURL+path, reader)
	if err != nil { return err }
	req.Header.Set("X-Ithute-Database-Gateway", a.token)
	if body != nil { req.Header.Set("Content-Type", "application/json") }
	resp, err := a.client.Do(req)
	if err != nil { return err }
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		payload, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("control plane returned %s: %s", resp.Status, strings.TrimSpace(string(payload)))
	}
	if out != nil { return json.NewDecoder(io.LimitReader(resp.Body, 2<<20)).Decode(out) }
	return nil
}

func (a *apiClient) heartbeat(ctx context.Context) error {
	var out map[string]any
	return a.request(ctx, http.MethodPost, "/hosting/database-gateway/heartbeat", heartbeatPayload{Version: version}, &out)
}
func (a *apiClient) routes(ctx context.Context) (snapshot, error) {
	var snap snapshot
	err := a.request(ctx, http.MethodGet, "/hosting/database-gateway/routes", nil, &snap)
	return snap, err
}
func (a *apiClient) ack(ctx context.Context, endpointID string, generation int64) error {
	if endpointID == "" || generation < 1 { return errors.New("invalid route acknowledgement") }
	var out map[string]any
	return a.request(ctx, http.MethodPost, "/hosting/database-gateway/routes/"+url.PathEscape(endpointID)+"/ack", ackPayload{Generation: generation}, &out)
}

func validateRoute(r route) error {
	if r.EndpointID == "" { return errors.New("route endpoint_id is required") }
	if r.ListenPort < 1024 || r.ListenPort > 65535 { return fmt.Errorf("route %s has invalid listen port", r.EndpointID) }
	if r.TargetPort < 1 || r.TargetPort > 65535 { return fmt.Errorf("route %s has invalid target port", r.EndpointID) }
	if strings.TrimSpace(r.TargetHost) == "" || strings.ContainsAny(r.TargetHost, " \t\r\n\x00") {
		return fmt.Errorf("route %s has invalid target host", r.EndpointID)
	}
	if r.Generation < 1 { return fmt.Errorf("route %s has invalid generation", r.EndpointID) }
	return nil
}

func validateSnapshot(s snapshot) error {
	endpoints := map[string]struct{}{}
	ports := map[int]struct{}{}
	for _, r := range s.Routes {
		if err := validateRoute(r); err != nil { return err }
		if _, ok := endpoints[r.EndpointID]; ok { return fmt.Errorf("duplicate endpoint %s", r.EndpointID) }
		if _, ok := ports[r.ListenPort]; ok { return fmt.Errorf("duplicate listen port %d", r.ListenPort) }
		endpoints[r.EndpointID] = struct{}{}
		ports[r.ListenPort] = struct{}{}
	}
	return nil
}

type routeTarget struct {
	mu sync.RWMutex
	r route
}
func (t *routeTarget) get() route { t.mu.RLock(); defer t.mu.RUnlock(); return t.r }
func (t *routeTarget) set(r route) { t.mu.Lock(); t.r = r; t.mu.Unlock() }

type activeRoute struct {
	endpointID string
	listenPort int
	target *routeTarget
	listener net.Listener
	cancel context.CancelFunc
}
type routeManager struct {
	mu sync.Mutex
	bindIP string
	dialTimeout time.Duration
	routes map[string]*activeRoute
}
func newRouteManager(bindIP string, dialTimeout time.Duration) *routeManager {
	return &routeManager{bindIP: bindIP, dialTimeout: dialTimeout, routes: make(map[string]*activeRoute)}
}

func (m *routeManager) apply(ctx context.Context, snap snapshot) ([]route, error) {
	if err := validateSnapshot(snap); err != nil { return nil, err }
	m.mu.Lock()
	defer m.mu.Unlock()
	desired := make(map[string]route, len(snap.Routes))
	for _, r := range snap.Routes { desired[r.EndpointID] = r }
	for id, current := range m.routes {
		next, ok := desired[id]
		if !ok || next.ListenPort != current.listenPort {
			current.cancel()
			_ = current.listener.Close()
			delete(m.routes, id)
		}
	}
	applied := make([]route, 0, len(snap.Routes))
	for _, r := range snap.Routes {
		if current, ok := m.routes[r.EndpointID]; ok {
			current.target.set(r)
			applied = append(applied, r)
			continue
		}
		address := net.JoinHostPort(m.bindIP, strconv.Itoa(r.ListenPort))
		ln, err := net.Listen("tcp", address)
		if err != nil { return nil, fmt.Errorf("listen %s for route %s: %w", address, r.EndpointID, err) }
		routeCtx, cancel := context.WithCancel(ctx)
		entry := &activeRoute{endpointID: r.EndpointID, listenPort: r.ListenPort, target: &routeTarget{r: r}, listener: ln, cancel: cancel}
		m.routes[r.EndpointID] = entry
		go m.acceptLoop(routeCtx, entry)
		applied = append(applied, r)
	}
	return applied, nil
}

func (m *routeManager) acceptLoop(ctx context.Context, ar *activeRoute) {
	for {
		conn, err := ar.listener.Accept()
		if err != nil {
			select {
			case <-ctx.Done(): return
			default:
				log.Printf("accept endpoint=%s error=%v", ar.endpointID, err)
				time.Sleep(100 * time.Millisecond)
				continue
			}
		}
		go m.proxyConnection(ctx, conn, ar.target)
	}
}

func (m *routeManager) proxyConnection(ctx context.Context, client net.Conn, target *routeTarget) {
	defer client.Close()
	r := target.get()
	address := net.JoinHostPort(r.TargetHost, strconv.Itoa(r.TargetPort))
	dialer := net.Dialer{Timeout: m.dialTimeout, KeepAlive: 30 * time.Second}
	upstream, err := dialer.DialContext(ctx, "tcp", address)
	if err != nil {
		log.Printf("dial endpoint=%s target=%s error=%v", r.EndpointID, address, err)
		return
	}
	defer upstream.Close()
	done := make(chan struct{}, 2)
	copyOne := func(dst, src net.Conn) {
		_, _ = io.Copy(dst, src)
		if tcp, ok := dst.(*net.TCPConn); ok { _ = tcp.CloseWrite() }
		done <- struct{}{}
	}
	go copyOne(upstream, client)
	go copyOne(client, upstream)
	select {
	case <-ctx.Done():
	case <-done:
		<-done
	}
}

func (m *routeManager) close() {
	m.mu.Lock()
	defer m.mu.Unlock()
	for id, r := range m.routes {
		r.cancel()
		_ = r.listener.Close()
		delete(m.routes, id)
	}
}

func run(ctx context.Context, cfg config) error {
	api := &apiClient{baseURL: cfg.APIURL, token: cfg.Token, client: &http.Client{Timeout: 15 * time.Second}}
	manager := newRouteManager(cfg.BindIP, cfg.DialTimeout)
	defer manager.close()
	ticker := time.NewTicker(cfg.PollInterval)
	defer ticker.Stop()

	syncRoutes := func() {
		callCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
		defer cancel()
		if err := api.heartbeat(callCtx); err != nil { log.Printf("gateway heartbeat failed: %v", err); return }
		snap, err := api.routes(callCtx)
		if err != nil { log.Printf("route snapshot failed: %v", err); return }
		applied, err := manager.apply(ctx, snap)
		if err != nil { log.Printf("route apply failed: %v", err); return }
		for _, r := range applied {
			if err := api.ack(callCtx, r.EndpointID, r.Generation); err != nil {
				log.Printf("route ack endpoint=%s generation=%d failed: %v", r.EndpointID, r.Generation, err)
			}
		}
	}

	syncRoutes()
	for {
		select {
		case <-ctx.Done(): return nil
		case <-ticker.C: syncRoutes()
		}
	}
}

func main() {
	cfg, err := loadConfig()
	if err != nil { log.Fatal(err) }
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	if err := run(ctx, cfg); err != nil { log.Fatal(err) }
}
