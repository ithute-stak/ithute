"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck,
  Building2,
  CheckCircle2,
  Clock3,
  Mail,
  RefreshCw,
  ShieldCheck,
  UserRound,
  XCircle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Application = {
  tenant_id: string;
  company_name: string;
  slug: string;
  status: "pending" | "approved" | "rejected";
  requested_plan_code?: string | null;
  applicant: {
    user_id?: string | null;
    full_name?: string | null;
    email?: string | null;
    email_verified: boolean;
  };
  created_at?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string | null;
};

type Tab = "pending" | "approved" | "rejected";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function PlanBadge({ code }: { code?: string | null }) {
  return <span className="rounded-full border border-[#e1e8e4] bg-[#f7faf8] px-2.5 py-1 text-[9px] font-black uppercase tracking-[.08em] text-[#577068]">{code || "No plan"}</span>;
}

export default function CustomerApplicationsPage() {
  const [tab, setTab] = useState<Tab>("pending");
  const [items, setItems] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/platform/customer-applications?status=${tab}`, {
        credentials: "include",
        cache: "no-store",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(body.detail || "Unable to load customer applications"));
      setItems(body.items || []);
    } catch (caught) {
      setItems([]);
      setError(caught instanceof Error ? caught.message : "Unable to load customer applications");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  async function approve(item: Application) {
    setBusyId(item.tenant_id);
    setError("");
    try {
      const response = await fetch(`${API}/platform/customer-applications/${item.tenant_id}/approve`, {
        method: "POST",
        credentials: "include",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(body.detail || "Unable to approve application"));
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to approve application");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(item: Application) {
    const trimmed = reason.trim();
    if (trimmed.length < 3) {
      setError("Please provide a short reason before rejecting this application.");
      return;
    }
    setBusyId(item.tenant_id);
    setError("");
    try {
      const response = await fetch(`${API}/platform/customer-applications/${item.tenant_id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ reason: trimmed }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(body.detail || "Unable to reject application"));
      setRejectingId(null);
      setReason("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reject application");
    } finally {
      setBusyId(null);
    }
  }

  const counts = useMemo(() => ({ current: items.length }), [items]);

  return (
    <div className="mx-auto max-w-[1320px] space-y-6 px-4 py-5 sm:px-6 lg:px-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#123a38] px-6 py-7 text-white shadow-[0_22px_60px_rgba(18,58,56,.18)] sm:px-8">
        <div className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[#d8c56a]/10 blur-2xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[9px] font-black uppercase tracking-[.14em] text-[#d8c56a]"><ShieldCheck size={13} /> Platform owner control</div>
            <h1 className="mt-4 text-3xl font-black tracking-[-.045em] sm:text-4xl">Customer Applications</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/62">Review companies before they can provision Ithute hosting, DNS, mail or databases. The customer&apos;s 14-day trial starts only when you approve the application.</p>
          </div>
          <button onClick={() => void load()} disabled={loading} className="inline-flex min-h-11 items-center justify-center gap-2 self-start rounded-xl border border-white/12 bg-white/[.07] px-4 text-xs font-black text-white transition hover:bg-white/[.12] disabled:opacity-60"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh</button>
        </div>
      </section>

      <section className="rounded-2xl border border-[#dfe7e2] bg-white p-2 shadow-sm">
        <div className="flex flex-wrap gap-2">
          {(["pending", "approved", "rejected"] as Tab[]).map((value) => (
            <button key={value} onClick={() => setTab(value)} className={`rounded-xl px-4 py-2.5 text-xs font-black capitalize transition ${tab === value ? "bg-[#123a38] text-white shadow-sm" : "text-[#587068] hover:bg-[#f3f7f5]"}`}>{value}</button>
          ))}
          <span className="ml-auto self-center px-3 text-[10px] font-black uppercase tracking-[.1em] text-[#87958e]">{counts.current} {tab}</span>
        </div>
      </section>

      {error ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-bold leading-5 text-red-700">{error}</div> : null}

      {loading ? (
        <div className="grid min-h-52 place-items-center rounded-3xl border border-[#dfe7e2] bg-white text-sm font-semibold text-[#718078]">Loading applications…</div>
      ) : items.length === 0 ? (
        <div className="grid min-h-60 place-items-center rounded-3xl border border-dashed border-[#ccd9d2] bg-white p-8 text-center">
          <div><div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#edf4f1] text-[#285b55]"><Building2 size={21} /></div><h2 className="mt-4 text-lg font-black">No {tab} applications</h2><p className="mt-2 text-xs leading-5 text-[#718078]">This queue is clear.</p></div>
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {items.map((item) => {
            const busy = busyId === item.tenant_id;
            const rejecting = rejectingId === item.tenant_id;
            return (
              <article key={item.tenant_id} className="rounded-[24px] border border-[#dfe7e2] bg-white p-5 shadow-sm sm:p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><PlanBadge code={item.requested_plan_code} />{item.applicant.email_verified ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[9px] font-black uppercase tracking-[.07em] text-emerald-700"><BadgeCheck size={12} /> Email verified</span> : <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[9px] font-black uppercase tracking-[.07em] text-amber-700"><Clock3 size={12} /> Email pending</span>}</div>
                    <h2 className="mt-3 truncate text-xl font-black tracking-[-.035em] text-[#20342a]">{item.company_name}</h2>
                    <p className="mt-1 text-[10px] font-bold text-[#8a9891]">{item.slug}</p>
                  </div>
                  <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${item.status === "approved" ? "bg-emerald-50 text-emerald-700" : item.status === "rejected" ? "bg-red-50 text-red-700" : "bg-[#edf4f1] text-[#285b55]"}`}>{item.status === "approved" ? <CheckCircle2 size={20} /> : item.status === "rejected" ? <XCircle size={20} /> : <Building2 size={20} />}</div>
                </div>

                <div className="mt-5 grid gap-3 rounded-2xl bg-[#f8faf9] p-4 sm:grid-cols-2">
                  <div><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#89968f]">Applicant</p><p className="mt-1 flex items-center gap-2 text-xs font-bold"><UserRound size={13} className="text-[#658078]" />{item.applicant.full_name || "—"}</p></div>
                  <div><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#89968f]">Work email</p><p className="mt-1 flex items-center gap-2 break-all text-xs font-bold"><Mail size={13} className="shrink-0 text-[#658078]" />{item.applicant.email || "—"}</p></div>
                  <div className="sm:col-span-2"><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#89968f]">Submitted</p><p className="mt-1 text-xs font-bold">{formatDate(item.created_at)}</p></div>
                </div>

                {item.status === "rejected" && item.rejection_reason ? <div className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-xs leading-5 text-red-700"><b>Reason:</b> {item.rejection_reason}</div> : null}
                {item.status === "approved" ? <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-xs leading-5 text-emerald-700">Approved {formatDate(item.approved_at)}. Customer services and trial entitlement are active.</div> : null}

                {item.status === "pending" ? (
                  <div className="mt-5 border-t border-[#e8eeea] pt-5">
                    {rejecting ? (
                      <div className="rounded-2xl border border-red-100 bg-red-50/60 p-4">
                        <label className="text-[10px] font-black uppercase tracking-[.1em] text-red-700">Reason for rejection</label>
                        <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} maxLength={500} className="mt-2 w-full rounded-xl border border-red-200 bg-white p-3 text-xs font-semibold text-[#263b31] outline-none focus:ring-4 focus:ring-red-100" placeholder="Explain why this application cannot be approved…" />
                        <div className="mt-3 flex flex-wrap gap-2"><button disabled={busy} onClick={() => void reject(item)} className="rounded-xl bg-red-700 px-4 py-2.5 text-xs font-black text-white disabled:opacity-60">{busy ? "Rejecting…" : "Confirm rejection"}</button><button disabled={busy} onClick={() => { setRejectingId(null); setReason(""); }} className="rounded-xl border border-red-200 bg-white px-4 py-2.5 text-xs font-black text-red-700">Cancel</button></div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <button disabled={busy} onClick={() => void approve(item)} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#123a38] px-5 text-xs font-black text-white shadow-sm transition hover:bg-[#285b55] disabled:opacity-60"><Check size={15} /> {busy ? "Approving…" : "Approve & start trial"}</button>
                        <button disabled={busy} onClick={() => { setRejectingId(item.tenant_id); setReason(""); }} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-red-200 px-5 text-xs font-black text-red-700 transition hover:bg-red-50 disabled:opacity-60"><XCircle size={15} /> Reject</button>
                      </div>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
