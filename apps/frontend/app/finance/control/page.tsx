"use client";

import { useEffect, useMemo, useState } from "react";
import { Calculator, CheckSquare2, LockKeyhole, RotateCcw, Send, Undo2 } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const money = (minor = 0) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
async function api(path: string, init?: RequestInit) { return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } }); }

function currentPeriod() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }
function today() { return new Date().toISOString().slice(0, 10); }

type Period = { id: string; period: string; year: number; month: number; status: string; note: string; locked_at?: string | null };
type Summary = { period: string; invoice_count: number; gross_invoiced_minor: number; net_invoiced_minor: number; gross_collected_minor: number; refunded_minor: number; net_collected_minor: number; outstanding_minor: number; unsettled_invoice_count: number };
type TaxRate = { id: string; name: string; rate_percent: number; inclusive: boolean; active: boolean };
type Payment = { id: string; amount_minor: number; refunded_minor?: number; net_amount_minor?: number; payment_date: string; reference: string };
type Invoice = { id: string; invoice_number: string; client_name: string; status: string; outstanding_minor: number; payments: Payment[] };
type Refund = { id: string; invoice_id: string; payment_id: string; amount_minor: number; refund_date: string; reference: string; reason: string };

export default function FinanceControlPage() {
  const [email, setEmail] = useState(""); const [owner, setOwner] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const [period, setPeriod] = useState(currentPeriod()); const [periods, setPeriods] = useState<Period[]>([]); const [summary, setSummary] = useState<Summary | null>(null);
  const [taxRates, setTaxRates] = useState<TaxRate[]>([]); const [tax, setTax] = useState({ name: "", rate_percent: "", inclusive: false });
  const [invoices, setInvoices] = useState<Invoice[]>([]); const [refunds, setRefunds] = useState<Refund[]>([]); const [refund, setRefund] = useState({ payment_id: "", amount: "", refund_date: today(), reference: "", reason: "" });
  const [selected, setSelected] = useState<Record<string, boolean>>({}); const [resend, setResend] = useState(false);

  const [year, month] = period.split("-").map(Number);
  const periodRow = periods.find((row) => row.period === period);
  const paymentOptions = useMemo(() => invoices.flatMap((invoice) => (invoice.payments || []).map((payment) => ({ invoice, payment })).filter(({ payment }) => (payment.net_amount_minor ?? payment.amount_minor - (payment.refunded_minor || 0)) > 0)), [invoices]);
  const selectedIds = useMemo(() => Object.entries(selected).filter(([, on]) => on).map(([id]) => id), [selected]);

  async function load() {
    const [p, s, t, i, r] = await Promise.all([
      api(`/finance/control/periods?year=${year}`), api(`/finance/control/periods/${year}/${month}/summary`), api("/finance/control/tax-rates"), api("/finance/invoices?limit=100"), api("/finance/control/refunds"),
    ]);
    if (p.ok) setPeriods((await p.json()).items || []); if (s.ok) setSummary(await s.json()); if (t.ok) setTaxRates((await t.json()).items || []); if (i.ok) setInvoices((await i.json()).items || []); if (r.ok) setRefunds((await r.json()).items || []);
  }

  useEffect(() => { void (async () => { const me = await api("/auth/me"); if (!me.ok) return; const body = await me.json(); setEmail(body.email || ""); setOwner(Boolean(body.is_platform_owner)); if (body.is_platform_owner) await load(); })(); }, []);
  useEffect(() => { if (owner) void load(); }, [period, owner]);

  async function setPeriodStatus(lock: boolean) {
    const verb = lock ? "lock" : "reopen"; const promptText = lock ? `Lock ${period}? Financial records in this month will become read-only.` : `Reopen ${period}? This will allow financial changes again.`;
    if (!window.confirm(promptText)) return; setBusy(true); setMessage("");
    try { const r = await api(`/finance/control/periods/${year}/${month}/${verb}`, { method: "POST", body: JSON.stringify({ note: lock ? "Month-end close" : "Period reopened by platform owner" }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || `Unable to ${verb} period`)); setMessage(`${period} is now ${data.status}.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to update period"); } finally { setBusy(false); }
  }

  async function addTaxRate() {
    if (!tax.name.trim() || tax.rate_percent === "") return setMessage("Tax name and rate are required."); setBusy(true); setMessage("");
    try { const r = await api("/finance/control/tax-rates", { method: "POST", body: JSON.stringify({ name: tax.name.trim(), rate_percent: Number(tax.rate_percent), inclusive: tax.inclusive, active: true }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to add tax rate")); setTax({ name: "", rate_percent: "", inclusive: false }); setMessage("Tax rate added."); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to add tax rate"); } finally { setBusy(false); }
  }

  async function createRefund() {
    if (!refund.payment_id || !refund.amount || !refund.reason.trim()) return setMessage("Payment, amount and refund reason are required."); setBusy(true); setMessage("");
    try { const r = await api("/finance/control/refunds", { method: "POST", body: JSON.stringify({ payment_id: refund.payment_id, amount_minor: Math.round(Number(refund.amount) * 100), refund_date: refund.refund_date, method: "bank_transfer", reference: refund.reference.trim(), reason: refund.reason.trim() }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to record refund")); setRefund({ payment_id: "", amount: "", refund_date: today(), reference: "", reason: "" }); setMessage("Refund recorded and invoice balance recalculated."); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to record refund"); } finally { setBusy(false); }
  }

  async function bulkSend() {
    if (!selectedIds.length) return setMessage("Select at least one invoice."); if (!window.confirm(`${resend ? "Send/resend" : "Send"} ${selectedIds.length} selected invoice(s)?`)) return; setBusy(true); setMessage("");
    try { const r = await api("/finance/control/bulk/invoices/send", { method: "POST", body: JSON.stringify({ invoice_ids: selectedIds, resend }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Bulk send failed")); setMessage(`Bulk send completed: ${data.sent?.length || 0} sent, ${data.failed?.length || 0} skipped/failed.`); setSelected({}); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Bulk send failed"); } finally { setBusy(false); }
  }

  return <ControlShell title="Finance controls" subtitle="Month-end close, tax profiles, refunds and bulk invoice actions" userEmail={email}>
    {!owner ? <section className="surface-card p-6">Finance is restricted.</section> : <div className="space-y-4 pb-24">
      {message ? <div className="surface-card px-4 py-3 text-xs font-bold">{message}</div> : null}

      <section className="surface-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow-label">Month-end control</p><h1 className="mt-1 text-lg font-black">Accounting period close</h1><p className="mt-1 text-xs text-[var(--admin-muted)]">Once locked, invoices, payments, credit notes, expenses, bank reconciliation and refunds in that month are read-only.</p></div><label className="text-[10px] font-black uppercase">Period<input className="input mt-1" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} /></label></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Net invoiced</p><p className="mt-2 text-xl font-black">{money(summary?.net_invoiced_minor || 0)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Net collected</p><p className="mt-2 text-xl font-black">{money(summary?.net_collected_minor || 0)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Refunds</p><p className="mt-2 text-xl font-black">{money(summary?.refunded_minor || 0)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Outstanding</p><p className="mt-2 text-xl font-black">{money(summary?.outstanding_minor || 0)}</p><p className="mt-1 text-[10px]">{summary?.unsettled_invoice_count || 0} unsettled invoice(s)</p></div></div>
        <div className="mt-4 flex flex-wrap items-center gap-2"><span className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase ${periodRow?.status === "locked" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"}`}>{periodRow?.status || "open"}</span>{periodRow?.status === "locked" ? <button disabled={busy} onClick={() => void setPeriodStatus(false)} className="btn-secondary inline-flex items-center gap-2"><RotateCcw size={14} />Reopen period</button> : <button disabled={busy} onClick={() => void setPeriodStatus(true)} className="btn-primary inline-flex items-center gap-2"><LockKeyhole size={14} />Lock month</button>}</div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="surface-card p-5"><div className="flex items-center gap-2"><Calculator size={17} /><h2 className="font-black">Tax profiles</h2></div><p className="mt-1 text-xs text-[var(--admin-muted)]">Reusable tax percentages for invoice calculations. Existing invoices remain unchanged.</p><div className="mt-3 grid gap-2 sm:grid-cols-[1fr_140px_auto]"><input className="input" placeholder="Tax name e.g. VAT" value={tax.name} onChange={(e) => setTax({ ...tax, name: e.target.value })} /><input className="input" type="number" min="0" max="100" step="0.01" placeholder="Rate %" value={tax.rate_percent} onChange={(e) => setTax({ ...tax, rate_percent: e.target.value })} /><button disabled={busy} onClick={() => void addTaxRate()} className="btn-primary">Add</button></div><label className="mt-2 flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={tax.inclusive} onChange={(e) => setTax({ ...tax, inclusive: e.target.checked })} />Price is tax-inclusive</label><div className="mt-4 grid gap-2">{taxRates.map((row) => <div key={row.id} className="flex items-center justify-between rounded-xl border px-3 py-2"><div><p className="text-xs font-black">{row.name}</p><p className="text-[10px] text-[var(--admin-muted)]">{row.inclusive ? "Inclusive" : "Exclusive"}</p></div><span className="text-sm font-black">{row.rate_percent.toFixed(2)}%</span></div>)}</div></section>

        <section className="surface-card p-5"><div className="flex items-center gap-2"><Undo2 size={17} /><h2 className="font-black">Refund payment</h2></div><p className="mt-1 text-xs text-[var(--admin-muted)]">Refunds reduce net collections and reopen the invoice balance when appropriate.</p><div className="mt-3 grid gap-2"><select className="input" value={refund.payment_id} onChange={(e) => setRefund({ ...refund, payment_id: e.target.value })}><option value="">Select payment</option>{paymentOptions.map(({ invoice, payment }) => <option key={payment.id} value={payment.id}>{invoice.invoice_number} · {invoice.client_name} · refundable {money(payment.net_amount_minor ?? payment.amount_minor - (payment.refunded_minor || 0))}</option>)}</select><div className="grid grid-cols-2 gap-2"><input className="input" type="number" min="0.01" step="0.01" placeholder="Amount (M)" value={refund.amount} onChange={(e) => setRefund({ ...refund, amount: e.target.value })} /><input className="input" type="date" value={refund.refund_date} onChange={(e) => setRefund({ ...refund, refund_date: e.target.value })} /></div><input className="input" placeholder="Refund reference" value={refund.reference} onChange={(e) => setRefund({ ...refund, reference: e.target.value })} /><textarea className="input min-h-16" placeholder="Reason" value={refund.reason} onChange={(e) => setRefund({ ...refund, reason: e.target.value })} /><button disabled={busy} onClick={() => void createRefund()} className="btn-primary">Record refund</button></div></section>
      </div>

      <section className="surface-card overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><p className="eyebrow-label">Bulk operations</p><h2 className="mt-1 font-black">Invoice sending</h2></div><div className="flex items-center gap-2"><label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={resend} onChange={(e) => setResend(e.target.checked)} />Allow resend</label><button disabled={busy || !selectedIds.length} onClick={() => void bulkSend()} className="btn-primary inline-flex items-center gap-2"><Send size={14} />Send selected ({selectedIds.length})</button></div></div><div className="max-h-[420px] overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-white"><tr><th className="p-3"><CheckSquare2 size={14} /></th><th className="p-3">Invoice</th><th className="p-3">Client</th><th className="p-3">Status</th><th className="p-3 text-right">Outstanding</th></tr></thead><tbody>{invoices.map((invoice) => <tr key={invoice.id} className="border-t"><td className="p-3"><input type="checkbox" checked={Boolean(selected[invoice.id])} onChange={(e) => setSelected({ ...selected, [invoice.id]: e.target.checked })} /></td><td className="p-3 font-black">{invoice.invoice_number}</td><td className="p-3">{invoice.client_name}</td><td className="p-3 uppercase">{invoice.status}</td><td className="p-3 text-right font-black">{money(invoice.outstanding_minor)}</td></tr>)}</tbody></table></div></section>

      <section className="surface-card overflow-hidden"><div className="border-b p-4"><p className="eyebrow-label">Refund register</p><h2 className="mt-1 font-black">Processed refunds</h2></div><div className="overflow-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-3">Date</th><th className="p-3">Reference</th><th className="p-3">Reason</th><th className="p-3 text-right">Amount</th></tr></thead><tbody>{refunds.map((row) => <tr key={row.id} className="border-t"><td className="p-3">{row.refund_date}</td><td className="p-3">{row.reference || "—"}</td><td className="p-3">{row.reason}</td><td className="p-3 text-right font-black">{money(row.amount_minor)}</td></tr>)}</tbody></table></div></section>
    </div>}
  </ControlShell>;
}
