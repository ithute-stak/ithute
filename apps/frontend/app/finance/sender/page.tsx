"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Mail, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { financeRoleRank, useFinanceAccess } from "../_components/use-finance-access";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type SenderConfig = {
  configured: boolean;
  sender_email: string;
  smtp_username: string;
  smtp_host: string;
  smtp_port: number;
  security_mode: "starttls" | "ssl";
  has_password: boolean;
  verified: boolean;
  verified_at?: string | null;
  last_verification_error?: string | null;
};

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

export default function FinanceSenderPage() {
  const { email, allowed, role, loading: accessLoading } = useFinanceAccess();
  const isAdmin = financeRoleRank(role) >= 4;
  const [config, setConfig] = useState<SenderConfig | null>(null);
  const [senderEmail, setSenderEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [security, setSecurity] = useState<"starttls" | "ssl">("starttls");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!allowed || !isAdmin) return;
    void (async () => {
      const r = await api("/finance/sender");
      if (!r.ok) return;
      const data = (await r.json()) as SenderConfig;
      applyConfig(data);
    })();
  }, [allowed, isAdmin]);

  function applyConfig(data: SenderConfig) {
    setConfig(data);
    setSenderEmail(data.sender_email || "");
    setUsername(data.smtp_username || data.sender_email || "");
    setHost(data.smtp_host || "");
    setPort(String(data.smtp_port || 587));
    setSecurity(data.security_mode === "ssl" ? "ssl" : "starttls");
    setPassword("");
  }

  async function save() {
    if (!isAdmin) return setMessage("Finance Admin access is required.");
    if (!senderEmail.trim() || !host.trim() || !port.trim()) {
      setMessage("Sending email, SMTP host and port are required.");
      return;
    }
    if (!config?.has_password && !password) {
      setMessage("Enter the SMTP password for the first configuration.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const r = await api("/finance/sender", {
        method: "PUT",
        body: JSON.stringify({
          sender_email: senderEmail.trim(),
          smtp_username: username.trim() || senderEmail.trim(),
          smtp_password: password || null,
          smtp_host: host.trim(),
          smtp_port: Number(port),
          security_mode: security,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "Unable to save sender configuration"));
      applyConfig(data as SenderConfig);
      setMessage("Sending account saved. Verify it before sending invoices.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save sender configuration");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (!isAdmin) return setMessage("Finance Admin access is required.");
    setBusy(true);
    setMessage("");
    try {
      const r = await api("/finance/sender/verify", { method: "POST", body: "{}" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "SMTP verification failed"));
      applyConfig(data as SenderConfig);
      setMessage("SMTP authentication verified. Finance invoices can now be sent from this account.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "SMTP verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ControlShell title="Finance sender" subtitle="Configure and verify the email account used to send invoices" userEmail={email}>
      {accessLoading ? (
        <section className="surface-card p-6">Checking Finance access…</section>
      ) : !allowed || !isAdmin ? (
        <section className="surface-card p-6"><h1 className="text-xl font-black">Finance Admin access is required</h1></section>
      ) : (
        <div className="mx-auto max-w-4xl space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Link className="btn-secondary" href="/finance">← Back to Finance</Link>
            <span className={`rounded-full px-3 py-1 text-xs font-black ${config?.verified ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
              {config?.verified ? "Verified sender" : config?.configured ? "Verification required" : "Not configured"}
            </span>
          </div>

          <section className="surface-card overflow-hidden">
            <div className="border-b bg-gradient-to-r from-[#f7fbff] via-white to-[#f5fbf2] p-5">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-[#e9f4ff] p-3 text-[#082b58]"><Mail size={22} /></div>
                <div>
                  <p className="eyebrow-label">One-time sending account setup</p>
                  <h1 className="mt-1 text-2xl font-black">Invoice sending email</h1>
                  <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--admin-muted)]">The password is encrypted before it is stored in Ithute. It is never returned to this screen. Saving any changed SMTP setting removes verification until the account authenticates successfully again.</p>
                </div>
              </div>
            </div>

            <div className="space-y-4 p-5">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-xs font-bold">Sending email<input className="input mt-1" type="email" value={senderEmail} onChange={(e) => { setSenderEmail(e.target.value); if (!username) setUsername(e.target.value); }} placeholder="invoices@ithute.co.ls" /></label>
                <label className="text-xs font-bold">SMTP username<input className="input mt-1" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Usually the full email address" /></label>
              </div>
              <div className="grid gap-4 md:grid-cols-[1fr_140px_180px]">
                <label className="text-xs font-bold">SMTP host<input className="input mt-1" value={host} onChange={(e) => setHost(e.target.value)} placeholder="mail.ithute.co.ls" /></label>
                <label className="text-xs font-bold">Port<input className="input mt-1" type="number" min="1" max="65535" value={port} onChange={(e) => setPort(e.target.value)} /></label>
                <label className="text-xs font-bold">Security<select className="input mt-1" value={security} onChange={(e) => setSecurity(e.target.value as "starttls" | "ssl")}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option></select></label>
              </div>
              <label className="text-xs font-bold">SMTP password
                <div className="relative mt-1"><KeyRound className="absolute left-3 top-3 text-[var(--admin-muted)]" size={16} /><input className="input pl-10" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={config?.has_password ? "Stored securely — leave blank to keep it" : "Enter mailbox password"} /></div>
              </label>

              {config?.verified && config.verified_at ? (
                <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><CheckCircle2 className="mt-0.5 shrink-0" size={18} /><div><p className="font-black">SMTP authentication verified</p><p className="mt-1 text-xs">Verified {new Date(config.verified_at).toLocaleString()}. Invoice sending is enabled.</p></div></div>
              ) : config?.last_verification_error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">Last verification failed: {config.last_verification_error}</div>
              ) : null}

              {message ? <div className="rounded-2xl border bg-[#fafcfb] p-4 text-xs font-semibold">{message}</div> : null}

              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary" disabled={busy} onClick={() => void save()}><ShieldCheck size={15} />Save configuration</button>
                <button className="btn-primary" disabled={busy || !config?.configured} onClick={() => void verify()}><CheckCircle2 size={15} />Verify SMTP login</button>
              </div>
            </div>
          </section>
        </div>
      )}
    </ControlShell>
  );
}
