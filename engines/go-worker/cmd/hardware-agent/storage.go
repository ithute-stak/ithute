package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type StorageHealth struct {
	Device          string  `json:"device"`
	Protocol        string  `json:"protocol,omitempty"`
	Model           string  `json:"model,omitempty"`
	Serial          string  `json:"serial,omitempty"`
	HealthPassed    *bool   `json:"health_passed,omitempty"`
	TemperatureC    *float64 `json:"temperature_celsius,omitempty"`
	PercentageUsed  *uint64 `json:"percentage_used,omitempty"`
	MediaErrors     *uint64 `json:"media_errors,omitempty"`
	CriticalWarning *uint64 `json:"critical_warning,omitempty"`
}

type smartPayload struct {
	Device struct {
		Name     string `json:"name"`
		Protocol string `json:"protocol"`
	} `json:"device"`
	ModelName    string `json:"model_name"`
	SerialNumber string `json:"serial_number"`
	SmartStatus struct {
		Passed bool `json:"passed"`
	} `json:"smart_status"`
	Temperature struct {
		Current float64 `json:"current"`
	} `json:"temperature"`
	NVMe struct {
		CriticalWarning uint64 `json:"critical_warning"`
		PercentageUsed  uint64 `json:"percentage_used"`
		MediaErrors     uint64 `json:"media_errors"`
	} `json:"nvme_smart_health_information_log"`
}

func safeBlockDevices() []string {
	entries, err := os.ReadDir("/sys/block")
	if err != nil {
		return nil
	}
	devices := make([]string, 0, len(entries))
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, "loop") || strings.HasPrefix(name, "ram") {
			continue
		}
		if strings.ContainsAny(name, "/\\") || name == "" {
			continue
		}
		dev := filepath.Join("/dev", name)
		if _, err := os.Stat(dev); err == nil {
			devices = append(devices, dev)
		}
	}
	return devices
}

func boolPtr(value bool) *bool       { return &value }
func floatPtr(value float64) *float64 { return &value }
func uintPtr(value uint64) *uint64    { return &value }

func collectSmartStorage(parent context.Context, smartctl string) []StorageHealth {
	devices := safeBlockDevices()
	if len(devices) == 0 {
		return nil
	}
	if len(devices) > 64 {
		devices = devices[:64]
	}

	results := make([]StorageHealth, 0, len(devices))
	for _, device := range devices {
		ctx, cancel := context.WithTimeout(parent, 3*time.Second)
		cmd := exec.CommandContext(ctx, smartctl, "-a", "-j", device)
		output, err := cmd.Output()
		cancel()
		if err != nil || len(output) == 0 || len(output) > 2*1024*1024 {
			continue
		}

		health, err := parseSmartHealth(device, output)
		if err != nil {
			continue
		}
		results = append(results, health)
	}
	return results
}

func parseSmartHealth(device string, output []byte) (StorageHealth, error) {
	var payload smartPayload
	if err := json.Unmarshal(output, &payload); err != nil {
		return StorageHealth{}, err
	}
	health := StorageHealth{
		Device:   device,
		Protocol: payload.Device.Protocol,
		Model:    payload.ModelName,
		Serial:   payload.SerialNumber,
	}
	if bytesContainKey(output, `"smart_status"`) {
		health.HealthPassed = boolPtr(payload.SmartStatus.Passed)
	}
	if bytesContainKey(output, `"temperature"`) {
		health.TemperatureC = floatPtr(payload.Temperature.Current)
	}
	if bytesContainKey(output, `"nvme_smart_health_information_log"`) {
		health.PercentageUsed = uintPtr(payload.NVMe.PercentageUsed)
		health.MediaErrors = uintPtr(payload.NVMe.MediaErrors)
		health.CriticalWarning = uintPtr(payload.NVMe.CriticalWarning)
	}
	return health, nil
}

func bytesContainKey(raw []byte, key string) bool {
	return strings.Contains(string(raw), key)
}

func smartctlPath() (string, error) {
	for _, candidate := range []string{"/usr/sbin/smartctl", "/usr/bin/smartctl"} {
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("smartctl unavailable")
}
