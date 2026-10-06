package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

type SignedEnvelope struct {
	EnvelopeVersion int    `json:"envelope_version"`
	Algorithm       string `json:"algorithm"`
	AgentID         string `json:"agent_id"`
	IssuedAtUnix    int64  `json:"issued_at_unix"`
	Nonce           string `json:"nonce"`
	Payload         Sample `json:"payload"`
	Signature       string `json:"signature"`
}

type unsignedEnvelope struct {
	EnvelopeVersion int    `json:"envelope_version"`
	Algorithm       string `json:"algorithm"`
	AgentID         string `json:"agent_id"`
	IssuedAtUnix    int64  `json:"issued_at_unix"`
	Nonce           string `json:"nonce"`
	Payload         Sample `json:"payload"`
}

func validateWithRust(parent context.Context, validatorPath string, sample Sample) error {
	if validatorPath == "" {
		return nil
	}
	ctx, cancel := context.WithTimeout(parent, 2*time.Second)
	defer cancel()

	args := []string{
		fmt.Sprintf("%.0f", sample.UptimeSeconds),
		fmt.Sprintf("%.6f", sample.Load.One),
		fmt.Sprintf("%d", sample.Memory.TotalKB),
		fmt.Sprintf("%d", sample.Memory.AvailableKB),
		fmt.Sprintf("%d", sample.Memory.SwapTotalKB),
		fmt.Sprintf("%d", sample.Memory.SwapFreeKB),
		fmt.Sprintf("%d", sample.Thermal.ZonesSeen),
		fmt.Sprintf("%.6f", sample.Thermal.MaxCelsius),
		fmt.Sprintf("%.6f", sample.Pressure.CPUAvg10),
		fmt.Sprintf("%.6f", sample.Pressure.MemoryAvg10),
		fmt.Sprintf("%.6f", sample.Pressure.IOAvg10),
		fmt.Sprintf("%d", sample.Filesystem.RootTotalBytes),
		fmt.Sprintf("%d", sample.Filesystem.RootAvailableBytes),
		fmt.Sprintf("%d", sample.Block.Devices),
	}
	// #nosec G204 -- validatorPath is an operator-configured local Ithute binary; arguments are numeric telemetry values.
	cmd := exec.CommandContext(ctx, validatorPath, args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("rust telemetry validation failed: %s: %w", strings.TrimSpace(string(output)), err)
	}
	if strings.TrimSpace(string(output)) != "ok" {
		return fmt.Errorf("rust telemetry validator returned unexpected response")
	}
	return nil
}

func readSigningKey(path string) ([]byte, error) {
	if path == "" {
		return nil, fmt.Errorf("signing key file is required")
	}
	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("stat signing key: %w", err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("signing key path is a directory")
	}
	if info.Mode().Perm()&0o077 != 0 {
		return nil, fmt.Errorf("signing key file permissions must not allow group/world access")
	}
	// #nosec G304 -- path has been stat-checked above and must be owner-only before reading.
	key, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read signing key: %w", err)
	}
	key = []byte(strings.TrimSpace(string(key)))
	if len(key) < 32 {
		return nil, fmt.Errorf("signing key must contain at least 32 bytes")
	}
	if len(key) > 4096 {
		return nil, fmt.Errorf("signing key exceeds 4096-byte safety limit")
	}
	return key, nil
}

func validAgentID(value string) bool {
	if len(value) < 3 || len(value) > 128 {
		return false
	}
	for _, r := range value {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '-' || r == '_' || r == '.' || r == ':' {
			continue
		}
		return false
	}
	return true
}

func signSample(agentID string, key []byte, sample Sample) (SignedEnvelope, error) {
	if !validAgentID(agentID) {
		return SignedEnvelope{}, fmt.Errorf("invalid agent id")
	}
	nonceBytes := make([]byte, 16)
	if _, err := rand.Read(nonceBytes); err != nil {
		return SignedEnvelope{}, fmt.Errorf("generate nonce: %w", err)
	}
	unsigned := unsignedEnvelope{
		EnvelopeVersion: 1,
		Algorithm:       "HMAC-SHA256",
		AgentID:         agentID,
		IssuedAtUnix:    time.Now().Unix(),
		Nonce:           hex.EncodeToString(nonceBytes),
		Payload:         sample,
	}
	canonical, err := json.Marshal(unsigned)
	if err != nil {
		return SignedEnvelope{}, fmt.Errorf("marshal unsigned envelope: %w", err)
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write(canonical)
	return SignedEnvelope{
		EnvelopeVersion: unsigned.EnvelopeVersion,
		Algorithm:       unsigned.Algorithm,
		AgentID:         unsigned.AgentID,
		IssuedAtUnix:    unsigned.IssuedAtUnix,
		Nonce:           unsigned.Nonce,
		Payload:         sample,
		Signature:       hex.EncodeToString(mac.Sum(nil)),
	}, nil
}

func verifyEnvelope(envelope SignedEnvelope, key []byte) bool {
	unsigned := unsignedEnvelope{
		EnvelopeVersion: envelope.EnvelopeVersion,
		Algorithm:       envelope.Algorithm,
		AgentID:         envelope.AgentID,
		IssuedAtUnix:    envelope.IssuedAtUnix,
		Nonce:           envelope.Nonce,
		Payload:         envelope.Payload,
	}
	canonical, err := json.Marshal(unsigned)
	if err != nil {
		return false
	}
	provided, err := hex.DecodeString(envelope.Signature)
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write(canonical)
	return hmac.Equal(provided, mac.Sum(nil))
}
