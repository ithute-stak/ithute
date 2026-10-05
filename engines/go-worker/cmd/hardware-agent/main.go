package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"time"
)

type Sample struct {
	SchemaVersion  int     `json:"schema_version"`
	SampledAtUnix int64   `json:"sampled_at_unix"`
	UptimeSeconds float64 `json:"uptime_seconds"`
	Load struct {
		One     float64 `json:"one"`
		Five    float64 `json:"five"`
		Fifteen float64 `json:"fifteen"`
	} `json:"load"`
	Memory struct {
		TotalKB     uint64 `json:"total_kb"`
		AvailableKB uint64 `json:"available_kb"`
		SwapTotalKB uint64 `json:"swap_total_kb"`
		SwapFreeKB  uint64 `json:"swap_free_kb"`
	} `json:"memory"`
	CPU map[string]uint64 `json:"cpu"`
	Thermal struct {
		ZonesSeen  int     `json:"zones_seen"`
		MaxCelsius float64 `json:"max_celsius"`
	} `json:"thermal"`
}

func runProbe(ctx context.Context, path string) (Sample, error) {
	var sample Sample
	cmd := exec.CommandContext(ctx, path)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	stdout, err := cmd.Output()
	if err != nil {
		if stderr.Len() > 0 {
			return sample, fmt.Errorf("hardware probe failed: %s: %w", stderr.String(), err)
		}
		return sample, fmt.Errorf("hardware probe failed: %w", err)
	}
	if err := json.Unmarshal(bytes.TrimSpace(stdout), &sample); err != nil {
		return sample, fmt.Errorf("invalid probe JSON: %w", err)
	}
	if sample.SchemaVersion != 1 {
		return sample, fmt.Errorf("unsupported schema_version %d", sample.SchemaVersion)
	}
	return sample, nil
}

func main() {
	probe := flag.String("probe", "./engines/hardware-intelligence/build/ithute-hw-probe", "path to the read-only C hardware probe")
	interval := flag.Duration("interval", 15*time.Second, "sampling interval")
	once := flag.Bool("once", false, "collect one sample and exit")
	flag.Parse()

	if *interval < time.Second {
		fmt.Fprintln(os.Stderr, "hardware-agent: interval must be at least 1s")
		os.Exit(2)
	}

	writer := bufio.NewWriter(os.Stdout)
	defer writer.Flush()

	collect := func() error {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		sample, err := runProbe(ctx, *probe)
		if err != nil {
			return err
		}
		encoded, err := json.Marshal(sample)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(writer, string(encoded))
		writer.Flush()
		return err
	}

	if *once {
		if err := collect(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}

	ticker := time.NewTicker(*interval)
	defer ticker.Stop()
	for {
		if err := collect(); err != nil && !errors.Is(err, context.Canceled) {
			fmt.Fprintln(os.Stderr, err)
		}
		<-ticker.C
	}
}
