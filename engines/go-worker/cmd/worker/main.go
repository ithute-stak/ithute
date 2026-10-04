package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"
)

type status struct {
	Service      string   `json:"service"`
	Engine       string   `json:"engine"`
	Version      string   `json:"version"`
	Capabilities []string `json:"capabilities"`
}

var engineStatus = status{
	Service:      "ithute-go-worker",
	Engine:       "go",
	Version:      "0.1.0",
	Capabilities: []string{"health", "network-concurrency-foundation"},
}

func writeJSON(w http.ResponseWriter, code int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(value)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})
	mux.HandleFunc("GET /v1/capabilities", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, engineStatus)
	})

	server := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	log.Printf("starting %s %s", engineStatus.Service, engineStatus.Version)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("worker stopped: %v", err)
		os.Exit(1)
	}
}
