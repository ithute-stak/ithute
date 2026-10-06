package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

func postEnvelope(parent context.Context, endpoint string, token []byte, envelope SignedEnvelope) error {
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return fmt.Errorf("invalid telemetry endpoint")
	}
	if parsed.Scheme != "https" && parsed.Hostname() != "127.0.0.1" && parsed.Hostname() != "localhost" {
		return fmt.Errorf("telemetry endpoint must use HTTPS outside localhost")
	}

	body, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("marshal telemetry envelope: %w", err)
	}

	ctx, cancel := context.WithTimeout(parent, 8*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create telemetry request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Ithute-Server-Agent", strings.TrimSpace(string(token)))
	req.Header.Set("User-Agent", "ithute-hardware-agent/1")

	client := &http.Client{
		Timeout: 8 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	response, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("send telemetry: %w", err)
	}
	defer response.Body.Close()
	responseBody, _ := io.ReadAll(io.LimitReader(response.Body, 16*1024))
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("telemetry endpoint returned %d: %s", response.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	return nil
}
