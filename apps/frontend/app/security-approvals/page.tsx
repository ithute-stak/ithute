"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Clock3, RefreshCw, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Approval = {
  id: string; tenant_id?: string | null; action: string; resource_type: string; resource_id: string;
  status: string; requested_by_user_id: string; approved_by_user_id?: string | null;
  created_at: string; expires_at: string; approved_at?: string | null; executed_at?: string | null;
};

function statusClass(status: string) {
  if (status === "pending") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "approved") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "executed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

export default function SecurityApprovalsPage() {
  const [email, setEmail] = useState("");
  const [rows, setRows] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [me, data] = await Promise.all([
        apiJson<{ email?: string; is_platform_owner?: boolean }>("/auth/me", { ttlMs: 0, force: true }),
        apiJson<{ items: Approval[] }>("/security/approvals", { ttlMs: 0, force: true }),
      ]);
      if (!me.is_platform_owner) throw new Error("Platform owner access is required.");
      setEmail(me.email || ""); setRows(data.items || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load approval queue.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function approve(id: string) {
    setBusy(id); setError(""); setMessage("");
    try {
      await apiMutation("/security/approvals/" + id + "/approve", { method: "POST" }, ["/security/approvals"]);
      setMessage("Approval granted. The original requester can now execute the exact approved operation.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to approve request.");
    } finally { setBusy(""); }
  }

  return (
    <ControlShell title="Security approvals" subtitle="Two-person authorization for catastrophic operations" userEmail={email}>
      <div className="space-y-4">
        <section className="surface-card p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="text-[9px] font-black uppercase tracking-[.14em] text-[var(--admin-muted)]">Dual control</p><h1 className="mt-2 text-2xl font-black">Security approval queue</h1><p className="mt-1 max-w-3xl text-[10px] leading-5 text-[var(--admin-muted)]">A different platform owner must approve high-impact actions. Approval is short-lived, payload-bound and single-use.</p></div>
            <button className="btn-secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? "animate-spin" : ""}/>Refresh</button>
          </div>
        </section>
        {error ? <div className="surface-card border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div> : null}
        {message ? <div className="surface-card border-emerald-200 bg-emerald-50 p-3 text-xs font-bold text-emerald-700">{message}</div> : null}
        <section className="surface-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left text-[10px]">
              <thead><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]"><th className="p-3">Action</th><th className="p-3">Resource</th><th className="p-3">Requester</th><th className="p-3">Status</th><th className="p-3">Expires</th><th className="p-3">Control</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.id} className="border-b border-[var(--admin-line)] last:border-0">
                <td className="p-3"><p className="font-black">{row.action}</p><p className="font-mono text-[8px] text-[var(--admin-muted)]">{row.id}</p></td>
                <td className="p-3"><p className="font-bold">{row.resource_type}</p><p className="max-w-[220px] truncate font-mono text-[8px]">{row.resource_id}</p></td>
                <td className="p-3 font-mono text-[8px]">{row.requested_by_user_id}</td>
                <td className="p-3"><span className={"rounded-full border px-2 py-1 font-black uppercase " + statusClass(row.status)}>{row.status}</span></td>
                <td className="p-3 whitespace-nowrap"><Clock3 size={12} className="mr-1 inline"/>{new Date(row.expires_at).toLocaleString()}</td>
                <td className="p-3">{row.status === "pending" ? <button className="btn-primary" disabled={busy === row.id} onClick={() => void approve(row.id)}><ShieldCheck size={13}/>{busy === row.id ? "Approving…" : "Approve"}</button> : row.status === "approved" ? <span className="inline-flex items-center gap-1 text-blue-700"><CheckCircle2 size={13}/>Awaiting requester</span> : "—"}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!loading && !rows.length ? <div className="p-8 text-center text-xs text-[var(--admin-muted)]">No security approvals yet.</div> : null}
        </section>
      </div>
    </ControlShell>
  );
}
