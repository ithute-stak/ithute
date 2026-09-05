"use client";

import { useEffect, useState } from "react";
import { Activity, Database, Globe2, Radio, Server, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { MetricCard, PageHeader, StatusBadge } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type State = "good" | "warn" | "bad" | "neutral";
type Check = { label: string; detail: string; state: State; latency?: number };

export default function StatusPage() {
  const [email, setEmail] = useState("");
  const [checks, setChecks] = useState<Check[]>([]);
  const [last, setLast] = useState<Date | null>(null);
  const [environment, setEnvironment] = useState("—");

  async function run() {
    const next: Check[] = [];
    const start = performance.now();

    try {
      const r = await fetch(`${API.replace(/\/api\/v1$/, "")}/health/ready`, { cache: "no-store" });
      next.push({
        label: "Control plane API",
        detail: r.ok ? "Ready and accepting requests" : `HTTP ${r.status}`,
        state: r.ok ? "good" : "bad",
        latency: Math.round(performance.now() - start),
      });
    } catch {
      next.push({ label: "Control plane API", detail: "Unreachable from this browser", state: "bad" });
    }

    try {
      const r = await fetch(`${API}/auth/me`, { credentials: "include", cache: "no-store" });
      if (r.ok) {
        const me = await r.json();
        setEmail(me.email);
        next.push({ label: "Identity & sessions", detail: "Authenticated session is valid", state: "good" });
      } else {
        next.push({ label: "Identity & sessions", detail: "No active authenticated session", state: "warn" });
      }
    } catch {
      next.push({ label: "Identity & sessions", detail: "Identity endpoint unavailable", state: "bad" });
    }

    next.push(
      {
        label: "PostgreSQL",
        detail: "Covered by backend readiness probe",
        state: next[0]?.state === "good" ? "good" : "warn",
      },
      {
        label: "Redis",
        detail: "Covered by backend readiness probe",
        state: next[0]?.state === "good" ? "good" : "warn",
      },
      {
        label: "Authoritative DNS",
        detail: "PowerDNS zone health is checked from each managed domain",
        state: "neutral",
      },
      {
        label: "Mail data plane",
        detail: "Reserved for the mail infrastructure release",
        state: "neutral",
      },
    );

    setChecks(next);
    setLast(new Date());
  }

  useEffect(() => {
    setEnvironment(window.location.hostname === "localhost" ? "Local" : "Hosted");
    void run();
    const id = window.setInterval(() => void run(), 30000);
    return () => window.clearInterval(id);
  }, []);

  const healthy = checks.filter((c) => c.state === "good").length;

  return (
    <ControlShell title="Infrastructure status" subtitle="Operational health and service readiness" userEmail={email}>
      <div className="space-y-4">
        <PageHeader
          eyebrow="Operations"
          title="Status centre"
          description="A single place to see whether the control plane and its core dependencies are ready."
          actions={
            <button className="btn-secondary" onClick={() => void run()}>
              <Activity size={14} />
              Refresh checks
            </button>
          }
        />
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Healthy checks"
            value={`${healthy}/${checks.length}`}
            detail="Live browser-side service checks"
            status={healthy === checks.length ? "good" : healthy ? "warn" : "bad"}
          />
          <MetricCard
            label="API latency"
            value={`${checks[0]?.latency ?? "—"}${checks[0]?.latency !== undefined ? " ms" : ""}`}
            detail="Current readiness request"
            status={checks[0]?.state || "neutral"}
          />
          <MetricCard
            label="Environment"
            value={environment}
            detail="No sensitive infrastructure details exposed"
          />
          <MetricCard
            label="Last check"
            value={last ? last.toLocaleTimeString() : "—"}
            detail="Automatically refreshes every 30 seconds"
          />
        </section>
        <section className="surface-card overflow-hidden">
          <div className="divide-y divide-[var(--admin-line)]">
            {checks.map((c, i) => {
              const Icon = [Server, ShieldCheck, Database, Database, Globe2, Radio][i] || Server;
              return (
                <div key={c.label} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]">
                    <Icon size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-black text-[var(--admin-ink)]">{c.label}</p>
                    <p className="mt-1 text-[11px] text-[var(--admin-muted)]">{c.detail}</p>
                  </div>
                  <StatusBadge state={c.state}>
                    {c.state === "good"
                      ? "Operational"
                      : c.state === "bad"
                        ? "Unavailable"
                        : c.state === "warn"
                          ? "Attention"
                          : "Planned / contextual"}
                  </StatusBadge>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </ControlShell>
  );
}
