package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
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

var engineStatus = status{
	Service:      "ithute-go-worker",
	Engine:       "go",
	Version:      "0.2.0",
	Capabilities: []string{"health", "network-concurrency", "tcp-reachability"},
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

	server := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       6 * time.Second,
		WriteTimeout:      8 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	log.Printf("starting %s %s", engineStatus.Service, engineStatus.Version)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("worker stopped: %v", err)
		os.Exit(1)
	}
}
