"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Globe2, LockKeyhole, Network, RefreshCw, Server, ShieldCheck, TriangleAlert } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { PageHeader, StatusBadge, Toast } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean; mfa_enabled: boolean };
type Check = { ok: boolean; expected: string[]; actual: string[]; detail?: string };
type Setup = {
  mode: string;
  security_level: string;
  signup_enabled: boolean;
  setup_required: boolean;
  bootstrap_public_ip?: string;
  primary_domain?: string;
  panel_hostname?: string;
  api_hostname?: string;
  groupware_hostname?: string;
  mail_hostname?: string;
  nameserver_1?: string;
  nameserver_2?: string;
  nameserver_1_ip?: string;
  nameserver_2_ip?: string;
  acme_email?: string;
  redundancy_warning?: string;
  registrar_instructions?: {
    glue_records: { hostname?: string; ip?: string }[];
    delegate_nameservers: string[];
    reverse_dns: { ip?: string; ptr?: string; note: string };
  };
  verification?: { verified: boolean; checks: Record<string, Check> };
  urls?: { panel: string; api: string; groupware: string };
};

function modeLabel(mode: string) {
  if (mode === "domain_active") return "Domain active";
  if (mode === "domain_verified") return "DNS verified";
  if (mode === "domain_pending") return "Waiting for delegation";
  return "IP bootstrap";
}

export default function PlatformSetupPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");

  async function load() {
    const m = await fetch(`${API}/auth/me`, { credentials: "include" });
    if (m.status === 401) { router.replace("/login"); return; }
    if (!m.ok) return;
    const account = await m.json();
    setMe(account);
    if (!account.is_platform_owner) { router.replace("/dashboard"); return; }
    const r = await fetch(`${API}/platform/setup`, { credentials: "include" });
    if (r.ok) setSetup(await r.json());
  }

  useEffect(() => { void load(); }, []);

  async function configure(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy("configure"); setToast("");
    const data = new FormData(e.currentTarget);
    const body = {
      domain: String(data.get("domain") || ""),
      acme_email: String(data.get("acme_email") || ""),
      nameserver_2_ip: String(data.get("nameserver_2_ip") || "") || null,
    };
    const r = await fetch(`${API}/platform/setup/domain`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const payload = await r.json().catch(() => ({}));
    if (!r.ok) setToast(String(payload.detail || "Unable to provision the platform domain"));
    else { setSetup(payload); setToast("Authoritative zone provisioned. Complete the registrar delegation shown below."); }
    setBusy("");
  }

  async function verify() {
    setBusy("verify"); setToast("");
    const r = await fetch(`${API}/platform/setup/verify`, { method: "POST", credentials: "include" });
    const payload = await r.json().catch(() => ({}));
    if (!r.ok) setToast(String(payload.detail || "Unable to verify public DNS"));
    else { setSetup(payload); setToast(payload.verification?.verified ? "Public DNS delegation is verified." : "DNS is not fully delegated yet. Review the checks below."); }
    setBusy("");
  }

  async function activate() {
    setBusy("activate"); setToast("");
    try {
      const r = await fetch(`${API}/platform/setup/activate`, { method: "POST", credentials: "include" });
      const payload = await r.json().catch(() => ({}));
      if (!r.ok) setToast(String(payload.detail || "Unable to activate secure domain mode"));
      else { setSetup(payload); setToast(`Secure domain mode activated. Open ${payload.urls?.panel || "the new panel hostname"}.`); }
    } catch {
      setToast("The proxy reloaded during activation. Open the new HTTPS panel hostname to confirm the switch.");
    }
    setBusy("");
  }

  const checks = setup?.verification?.checks ? Object.entries(setup.verification.checks) : [];
  const active = setup?.mode === "domain_active";

  return (
    <ControlShell title="Platform domain" subtitle="Bootstrap on IP, then let Mailbox DNS configure its own domain" userEmail={me?.email}>
      <div className="space-y-4">
        <PageHeader
          eyebrow="Platform identity"
          title="Self-hosted domain activation"
          description="Start safely on the VPS IP. When you buy the permanent domain, Mailbox DNS creates its authoritative zone, generates registrar instructions, verifies public delegation, then switches the control plane to HTTPS with stronger session security. No Cloudflare dependency."
          actions={<StatusBadge state={active ? "good" : setup?.mode === "domain_verified" ? "good" : "warn"}>{modeLabel(setup?.mode || "bootstrap")}</StatusBadge>}
        />

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="surface-card p-4"><div className="flex items-center gap-2"><Server size={16}/><p className="text-xs font-black">Bootstrap address</p></div><code className="mt-3 block break-all text-xs">{setup?.bootstrap_public_ip || "Loading…"}</code><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">The raw IP is for platform-owner bootstrap. Public customer signup remains closed here.</p></div>
          <div className="surface-card p-4"><div className="flex items-center gap-2"><Globe2 size={16}/><p className="text-xs font-black">Primary domain</p></div><p className="mt-3 text-xs font-bold">{setup?.primary_domain || "Not configured yet"}</p><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">The platform domain is authoritative through Mailbox DNS itself.</p></div>
          <div className="surface-card p-4"><div className="flex items-center gap-2"><ShieldCheck size={16}/><p className="text-xs font-black">Security level</p></div><p className="mt-3 text-xs font-bold">{setup?.security_level === "hardened" ? "Hardened HTTPS" : "Restricted bootstrap"}</p><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Domain activation requires platform-owner MFA and verified DNS.</p></div>
        </section>

        {!active ? <form onSubmit={configure} className="surface-card p-4 sm:p-5">
          <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]"><Network size={18}/></div><div><p className="text-sm font-black">1. Configure the domain you purchased</p><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Mailbox DNS will create panel, API, mail, groupware and authoritative nameserver records automatically.</p></div></div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <label><span className="label">Primary domain</span><input className="input" name="domain" defaultValue={setup?.primary_domain || ""} placeholder="example.co.ls" required /></label>
            <label><span className="label">ACME / operations email</span><input className="input" name="acme_email" type="email" defaultValue={setup?.acme_email || me?.email || ""} required /></label>
            <label><span className="label">Independent ns2 public IP (optional now)</span><input className="input" name="nameserver_2_ip" defaultValue={setup?.nameserver_2_ip && setup.nameserver_2_ip !== setup.bootstrap_public_ip ? setup.nameserver_2_ip : ""} placeholder="Second DNS server IP" /></label>
          </div>
          <button className="btn-primary mt-4" disabled={Boolean(busy)}>{busy === "configure" ? "Provisioning…" : setup?.primary_domain ? "Reconcile platform DNS" : "Provision platform domain"}</button>
        </form> : null}

        {setup?.registrar_instructions ? <section className="surface-card p-4 sm:p-5">
          <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#f8f4df] text-[#806800]"><Globe2 size={18}/></div><div><p className="text-sm font-black">2. One-time registrar delegation</p><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">The authoritative zone is already in Mailbox DNS. The registrar controls the parent delegation, so set these glue/nameserver values there once.</p></div></div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">{setup.registrar_instructions.glue_records.map((item) => <div key={item.hostname} className="rounded-xl bg-[#f8faf8] p-3"><p className="eyebrow-label">Glue / child nameserver</p><code className="mt-1 block text-xs">{item.hostname} → {item.ip}</code></div>)}</div>
          <div className="mt-3 rounded-xl border border-[var(--admin-line)] p-3"><p className="eyebrow-label">Delegate the domain to</p><code className="mt-1 block text-xs">{setup.registrar_instructions.delegate_nameservers.join(" · ")}</code></div>
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] leading-5 text-amber-800"><b>Reverse DNS / PTR:</b> ask the VPS/IP provider to set {setup.registrar_instructions.reverse_dns.ip} → {setup.registrar_instructions.reverse_dns.ptr}. This record lives with the IP provider, not inside the forward DNS zone.</div>
          {setup.redundancy_warning ? <div className="mt-3 flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] leading-5 text-amber-800"><TriangleAlert size={15} className="mt-0.5 shrink-0" />{setup.redundancy_warning}</div> : null}
        </section> : null}

        {setup?.primary_domain ? <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-black">3. Verify public DNS</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Mailbox DNS checks NS delegation and the public A records from recursive DNS before allowing activation.</p></div><button className="btn-secondary" disabled={Boolean(busy)} onClick={() => void verify()}><RefreshCw size={14}/>{busy === "verify" ? "Checking…" : "Verify delegation"}</button></div>
          {checks.length ? <div className="mt-4 grid gap-2">{checks.map(([name, check]) => <div key={name} className="flex items-start gap-3 rounded-xl border border-[var(--admin-line)] p-3"><div className={check.ok ? "text-emerald-600" : "text-amber-600"}>{check.ok ? <CheckCircle2 size={16}/> : <TriangleAlert size={16}/>}</div><div className="min-w-0"><p className="break-all text-[10px] font-black">{name}</p><p className="mt-1 break-all text-[9px] text-[var(--admin-muted)]">Expected: {check.expected.join(", ")} · Actual: {check.actual.length ? check.actual.join(", ") : check.detail || "not visible yet"}</p></div></div>)}</div> : null}
        </section> : null}

        {setup?.mode === "domain_verified" || active ? <section className="surface-card p-4 sm:p-5">
          <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><LockKeyhole size={18}/></div><div className="flex-1"><p className="text-sm font-black">4. Activate hardened domain mode</p><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Activation reloads the internal reverse proxy, obtains public TLS certificates automatically, redirects raw-IP web traffic to the panel hostname, enables HSTS, and issues Secure cookies on HTTPS.</p>{!me?.mfa_enabled ? <p className="mt-2 text-[10px] font-bold text-amber-700">Platform-owner MFA is required. <Link href="/security" className="underline">Enable MFA in Security</Link> before activation.</p> : null}</div>{active ? <StatusBadge state="good">Active</StatusBadge> : <button className="btn-primary" disabled={Boolean(busy) || !me?.mfa_enabled} onClick={() => void activate()}>{busy === "activate" ? "Activating…" : "Activate HTTPS"}</button>}</div>
          {active && setup?.urls ? <div className="mt-4 grid gap-3 sm:grid-cols-3">{Object.entries(setup.urls).map(([label, url]) => <a key={label} href={url} className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-black text-emerald-800" target="_blank" rel="noreferrer">{label}: {url}</a>)}</div> : null}
        </section> : null}
      </div>
      {toast ? <Toast tone={toast.toLowerCase().includes("unable") || toast.toLowerCase().includes("waiting") ? "error" : "success"} message={toast} onClose={() => setToast("")} /> : null}
    </ControlShell>
  );
}
