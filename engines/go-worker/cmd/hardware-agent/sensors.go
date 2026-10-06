package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type MemoryReliability struct {
	Available         bool   `json:"available"`
	CorrectedErrors   uint64 `json:"corrected_errors"`
	UncorrectedErrors uint64 `json:"uncorrected_errors"`
	Controllers       int    `json:"controllers"`
}

type BMCSummary struct {
	Available       bool     `json:"available"`
	SensorCount     int      `json:"sensor_count"`
	CriticalCount   int      `json:"critical_count"`
	WarningCount    int      `json:"warning_count"`
	MaxTempC        *float64 `json:"max_temp_celsius,omitempty"`
	MinFanRPM       *float64 `json:"min_fan_rpm,omitempty"`
	FaultySensors   []string `json:"faulty_sensors,omitempty"`
}

func readUintFile(path string) (uint64, bool) {
	// #nosec G304 -- callers pass only fixed EDAC sysfs paths rooted under /sys/devices/system/edac.
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, false
	}
	value, err := strconv.ParseUint(strings.TrimSpace(string(raw)), 10, 64)
	return value, err == nil
}

func collectEDAC() MemoryReliability {
	base := "/sys/devices/system/edac/mc"
	entries, err := os.ReadDir(base)
	if err != nil {
		return MemoryReliability{}
	}
	var result MemoryReliability
	for _, entry := range entries {
		if !entry.IsDir() || !strings.HasPrefix(entry.Name(), "mc") {
			continue
		}
		controller := filepath.Join(base, entry.Name())
		ce, ceOK := readUintFile(filepath.Join(controller, "ce_count"))
		ue, ueOK := readUintFile(filepath.Join(controller, "ue_count"))
		if !ceOK && !ueOK {
			continue
		}
		result.Available = true
		result.Controllers++
		result.CorrectedErrors += ce
		result.UncorrectedErrors += ue
	}
	return result
}

func ipmitoolPath() string {
	for _, candidate := range []string{"/usr/bin/ipmitool", "/usr/sbin/ipmitool"} {
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate
		}
	}
	return ""
}

func collectBMC(parent context.Context, path string) BMCSummary {
	if path == "" {
		return BMCSummary{}
	}
	ctx, cancel := context.WithTimeout(parent, 4*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, "-c", "sensor")
	output, err := cmd.Output()
	if err != nil || len(output) == 0 || len(output) > 1024*1024 {
		return BMCSummary{}
	}

	result := BMCSummary{Available: true, FaultySensors: make([]string, 0, 8)}
	scanner := bufio.NewScanner(strings.NewReader(string(output)))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		parts := strings.Split(line, ",")
		if len(parts) < 4 {
			continue
		}
		name := strings.Trim(strings.TrimSpace(parts[0]), "\"")
		valueText := strings.Trim(strings.TrimSpace(parts[1]), "\"")
		unit := strings.ToLower(strings.Trim(strings.TrimSpace(parts[2]), "\""))
		status := strings.ToLower(strings.Trim(strings.TrimSpace(parts[3]), "\""))
		result.SensorCount++

		if strings.Contains(status, "cr") || strings.Contains(status, "nr") || strings.Contains(status, "fail") {
			result.CriticalCount++
			if len(result.FaultySensors) < 8 {
				result.FaultySensors = append(result.FaultySensors, name)
			}
		} else if strings.Contains(status, "nc") || strings.Contains(status, "warn") {
			result.WarningCount++
		}

		value, parseErr := strconv.ParseFloat(valueText, 64)
		if parseErr != nil {
			continue
		}
		if strings.Contains(unit, "degrees c") || unit == "c" {
			if result.MaxTempC == nil || value > *result.MaxTempC {
				v := value
				result.MaxTempC = &v
			}
		}
		if strings.Contains(unit, "rpm") && value > 0 {
			if result.MinFanRPM == nil || value < *result.MinFanRPM {
				v := value
				result.MinFanRPM = &v
			}
		}
	}
	return result
}

func validateReliability(sample Sample) error {
	if sample.MemoryReliability.Controllers < 0 || sample.BMC.SensorCount < 0 {
		return fmt.Errorf("invalid hardware reliability counters")
	}
	return nil
}
