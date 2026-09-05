"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, ExternalLink, KeyRound, RefreshCw, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Me = { email?: string; full_name?: string; is_platform_owner?: boolean; mfa_enabled?: boolean };
type App = { id: string; name: string; category: string; public_url?: string | null; status: string; license?: { plan: string; status: string; features: Record<string, unknown> } };
type Notice = { id: string; product_id: string; title: string; body: string; category: string; action_url?: string | null; read_at?: string | null; created_at: string };

export default function IthuteAccountPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [apps, setApps] = useState<App[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [account, applicationRows, notificationRows] = await Promise.all([
        apiJson<Me>("/auth/me", { ttlMs: 0, force: true }),
        apiJson<App[]>("/platform/ithute/me/apps", { ttlMs: 0, force: true }),
        apiJson<Notice[]>("/platform/ithute/me/notifications?limit=50", { ttlMs: 0, force: true }),
      ]);
      setMe(account); setApps(applicationRows); setNotices(notificationRows);
    } catch { setError("Unable to load the Ithute account workspace."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function markRead(id: string) {
    try {
      await apiMutation(`/platform/ithute/me/notifications/${id}/read`, { method: "POST", credentials: "include" });
      setNotices(rows => rows.map(row => row.id === id ? { ...row, read_at: new Date().toISOString() } : row));
    } catch { setError("Unable to update the notification."); }
  }

  const unread = notices.filter(item => !item.read_at).length;

  return (
    <ControlShell title="Ithute Account" subtitle="One identity, permitted applications and persistent notifications" userEmail={me?.email}>
      <div className="space-y-5">
        <section className="surface-card p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="text-[9px] font-black uppercase tracking-[.14em] text-[var(--admin-muted)]">Central identity</p><h1 className="mt-2 text-2xl font-black">{me?.full_name || me?.email || "Ithute Account"}</h1><p className="mt-2 text-[11px] text-[var(--admin-muted)]">Applications are licensed centrally; each application still owns its own roles and business data.</p></div>
            <div className="flex flex-wrap gap-2"><a href="https://auth.ithute.co.ls/account" target="_blank" rel="noreferrer" className="btn-primary"><KeyRound size={14} />Manage password, MFA & devices</a><button className="btn-secondary" disabled={loading} onClick={() => void load()}><RefreshCw size={14} className={loading ? "animate-spin" : ""} />Refresh</button></div>
          </div>
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center gap-2"><ShieldCheck size={16} /><h2 className="text-sm font-black">App Launcher</h2></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{apps.map(app => <a key={app.id} href={app.public_url || "#"} target={app.public_url ? "_blank" : undefined} rel="noreferrer" className="rounded-2xl border border-[var(--admin-line)] p-4 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-black">{app.name}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{app.category} · {app.status}</p></div>{app.public_url ? <ExternalLink size={14} /> : null}</div><div className="mt-4 rounded-xl bg-[#f7faf8] p-3 text-[9px]"><span className="font-black">License:</span> {app.license?.plan || (me?.is_platform_owner ? "platform owner" : "default")} · {app.license?.status || "active"}</div></a>)}</div>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><Bell size={16} /><h2 className="text-sm font-black">Notification Centre</h2></div><span className="rounded-full bg-[#eef5f2] px-2.5 py-1 text-[9px] font-black text-[var(--admin-pine)]">{unread} unread</span></div>
          <div className="mt-4 space-y-2">{notices.map(item => <article key={item.id} className={`rounded-xl border p-4 ${item.read_at ? "border-[var(--admin-line)] bg-white" : "border-[#b8d7cb] bg-[#f3f9f6]"}`}><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-[10px] font-black">{item.title}</p><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">{item.body}</p><p className="mt-2 text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]">{item.product_id} · {item.category} · {new Date(item.created_at).toLocaleString()}</p></div><div className="flex gap-2">{item.action_url ? <a className="btn-secondary" href={item.action_url}>Open</a> : null}{!item.read_at ? <button className="btn-secondary" onClick={() => void markRead(item.id)}>Mark read</button> : null}</div></div></article>)}{!notices.length && !loading ? <p className="py-8 text-center text-[11px] text-[var(--admin-muted)]">No platform notifications yet.</p> : null}</div>
        </section>
      </div>
    </ControlShell>
  );
}
