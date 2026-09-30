"use client";

import { useEffect, useState } from "react";
import { CircleDollarSign, Download, FileMinus2, ReceiptText, Search, Send, Trash2, XCircle } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Payment = { id: string; amount_minor: number; payment_date: string; method: string; reference: string };
type Credit = { id: string; credit_number: string; amount_minor: number; reason: string };
type Invoice = {
  id: string; invoice_number: string; client_name: string; recipient_email: string; total_minor: number;
  credited_minor: number; adjusted_total_minor: number; paid_minor: number; outstanding_minor: number;
  due_date: string; status: string; last_error?: string | null; payments?: Payment[]; credit_notes?: Credit[];
};
type Dashboard = { active_clients: number; invoice_count: number; month_invoiced_minor: number; month_collected_minor: number; credited_minor?: number; outstanding_minor: number; overdue_minor: number; overdue_count: number };

async function api(path: string, init?: RequestInit) { return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } }); }
const money = (minor = 0) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function CollectionsPage() {
  const [email, setEmail] = useState(""); const [owner, setOwner] = useState(false); const [items, setItems] = useState<Invoice[]>([]); const [dashboard, setDashboard] = useState<Dashboard | null>(null); const [query, setQuery] = useState(""); const [status, setStatus] = useState(""); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);

  useEffect(() => { void (async () => { const me = await api("/auth/me"); if (!me.ok) return; const body = await me.json(); setEmail(body.email || ""); setOwner(Boolean(body.is_platform_owner)); if (body.is_platform_owner) await load(); })(); }, []);

  async function load(q = query, s = status) {
    const p = new URLSearchParams(); if (q.trim()) p.set("q", q.trim()); if (s) p.set("status", s); const suffix = p.size ? `?${p}` : "";
    const [a, b] = await Promise.all([api(`/finance/invoices${suffix}`), api("/finance/dashboard")]); if (a.ok) setItems((await a.json()).items || []); if (b.ok) setDashboard(await b.json());
  }

  async function download(path: string, filename: string) {
    const r = await fetch(`${API}${path}`, { credentials: "include" }); if (!r.ok) { const data = await r.json().catch(() => ({})); setMessage(String(data.detail || "Unable to download document")); return; }
    const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
  }

  async function payment(invoice: Invoice) {
    const amount = Number(window.prompt(`Payment for ${invoice.invoice_number}. Outstanding ${money(invoice.outstanding_minor)}. Enter amount:`, (invoice.outstanding_minor / 100).toFixed(2)));
    if (!Number.isFinite(amount) || amount <= 0) return;
    const reference = window.prompt("Payment reference:", invoice.invoice_number) || ""; const method = window.prompt("Payment method:", "bank_transfer") || "bank_transfer";
    setBusy(true); try {
      const r = await api(`/finance/invoices/${invoice.id}/payments`, { method: "POST", body: JSON.stringify({ amount_minor: Math.round(amount * 100), payment_date: new Date().toISOString().slice(0, 10), method, reference, note: "" }) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to record payment"));
      setMessage(`Payment recorded on ${invoice.invoice_number}. Receipt is ready.`); await load();
      if (data.payment?.id && window.confirm("Payment saved. Download the official receipt now?")) await download(`/finance/payments/${data.payment.id}/receipt.pdf`, `Receipt-${invoice.invoice_number}.pdf`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to record payment"); } finally { setBusy(false); }
  }

  async function credit(invoice: Invoice) {
    const max = Math.max(0, (invoice.total_minor || 0) - (invoice.credited_minor || 0));
    const amount = Number(window.prompt(`Credit note for ${invoice.invoice_number}. Enter credit amount (maximum ${money(max)}):`, (Math.min(invoice.outstanding_minor || max, max) / 100).toFixed(2)));
    if (!Number.isFinite(amount) || amount <= 0) return;
    const reason = window.prompt("Reason for credit note:", "Service adjustment") || ""; if (!reason.trim()) return;
    setBusy(true); try {
      const r = await api(`/finance/invoices/${invoice.id}/credit-notes`, { method: "POST", body: JSON.stringify({ amount_minor: Math.round(amount * 100), reason }) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to issue credit note"));
      setMessage(`${data.credit_number} issued against ${invoice.invoice_number}.`); await load();
      if (data.id && window.confirm("Credit note created. Download its PDF now?")) await download(`/finance/credit-notes/${data.id}/pdf`, `${data.credit_number}.pdf`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to issue credit note"); } finally { setBusy(false); }
  }

  async function send(invoice: Invoice, resend: boolean) { setBusy(true); try { const r = await api(`/finance/invoices/${invoice.id}/send`, { method: "POST", body: JSON.stringify({ resend }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to send invoice")); setMessage(`${invoice.invoice_number} sent.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to send invoice"); } finally { setBusy(false); } }
  async function cancel(invoice: Invoice) { if (!window.confirm(`Cancel ${invoice.invoice_number}?`)) return; setBusy(true); try { const r = await api(`/finance/invoices/${invoice.id}/cancel`, { method: "POST" }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to cancel")); setMessage(`${invoice.invoice_number} cancelled.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to cancel"); } finally { setBusy(false); } }
  async function remove(invoice: Invoice) { if (!window.confirm(`Permanently delete ${invoice.invoice_number}?`)) return; setBusy(true); try { const r = await api(`/finance/invoices/${invoice.id}`, { method: "DELETE" }); if (!r.ok) throw new Error("Unable to delete invoice"); setMessage(`${invoice.invoice_number} deleted.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to delete"); } finally { setBusy(false); } }

  const badge = (s: string) => s === "paid" || s === "credited" ? "bg-[#e7f8ed] text-[#116a38]" : s === "partial" ? "bg-[#fff7df] text-[#8a6410]" : s === "overdue" || s === "failed" ? "bg-[#fff0ef] text-[#a43a34]" : s === "cancelled" ? "bg-[#efefef] text-[#666]" : s === "sent" ? "bg-[#e9f7ee] text-[#146b3a]" : "bg-[#eef3f7] text-[#526474]";

  return <ControlShell title="Finance collections" subtitle="Payments, receipts, credit notes and overdue invoices" userEmail={email}>
    {!owner ? <section className="surface-card p-6">Finance is restricted.</section> : <div className="space-y-4">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Active clients</p><p className="mt-2 text-xl font-black">{dashboard?.active_clients ?? 0}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">This month invoiced</p><p className="mt-2 text-xl font-black">{money(dashboard?.month_invoiced_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">This month collected</p><p className="mt-2 text-xl font-black">{money(dashboard?.month_collected_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Credits issued</p><p className="mt-2 text-xl font-black">{money(dashboard?.credited_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Outstanding</p><p className="mt-2 text-xl font-black">{money(dashboard?.outstanding_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Overdue</p><p className="mt-2 text-xl font-black">{money(dashboard?.overdue_minor)}</p><p className="text-[9px] text-[var(--admin-muted)]">{dashboard?.overdue_count ?? 0} invoices</p></div>
      </section>
      {message ? <div className="surface-card p-3 text-xs font-bold">{message}</div> : null}
      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><p className="eyebrow-label">Collections register</p><h1 className="mt-1 font-black">Invoices, payments & credits</h1></div><div className="flex gap-2"><div className="flex items-center gap-2 rounded-xl border px-3"><Search size={14} /><input className="bg-transparent py-2 text-xs outline-none" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void load(e.currentTarget.value, status); }} placeholder="Search invoice or client" /></div><select className="input max-w-40" value={status} onChange={(e) => { setStatus(e.target.value); void load(query, e.target.value); }}><option value="">All</option><option value="draft">Draft</option><option value="sent">Sent</option><option value="partial">Partial</option><option value="paid">Paid</option><option value="credited">Credited</option><option value="overdue">Overdue</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option></select></div></div>
        <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Invoice</th><th className="p-3">Client</th><th className="p-3">Original</th><th className="p-3">Credits</th><th className="p-3">Paid</th><th className="p-3">Outstanding</th><th className="p-3">Due</th><th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead><tbody>{items.map((x) => <tr key={x.id} className="border-t align-top"><td className="p-3 font-mono font-bold">{x.invoice_number}<p className="mt-1 font-sans text-[9px] font-normal text-[var(--admin-muted)]">{x.recipient_email}</p></td><td className="p-3 font-bold">{x.client_name}</td><td className="p-3 font-black">{money(x.total_minor)}</td><td className="p-3">{money(x.credited_minor)}</td><td className="p-3">{money(x.paid_minor)}</td><td className="p-3 font-black">{money(x.outstanding_minor)}</td><td className="p-3">{new Date(`${x.due_date}T00:00:00`).toLocaleDateString()}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${badge(x.status)}`}>{x.status}</span>{x.last_error ? <p className="mt-1 max-w-56 text-[9px] text-[#a43a34]">{x.last_error}</p> : null}</td><td className="p-3"><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => void download(`/finance/invoices/${x.id}/pdf`, `${x.invoice_number}.pdf`)}><Download size={13} />PDF</button>{x.payments?.length ? <button className="btn-secondary" onClick={() => { const p = x.payments![x.payments!.length - 1]; void download(`/finance/payments/${p.id}/receipt.pdf`, `Receipt-${x.invoice_number}.pdf`); }}><ReceiptText size={13} />Receipt</button> : null}{!["paid", "cancelled", "credited"].includes(x.status) ? <button className="btn-secondary" disabled={busy} onClick={() => void payment(x)}><CircleDollarSign size={13} />Payment</button> : null}{x.status !== "cancelled" ? <button className="btn-secondary" disabled={busy} onClick={() => void credit(x)}><FileMinus2 size={13} />Credit</button> : null}{!["paid", "cancelled", "credited"].includes(x.status) ? <button className="btn-secondary" disabled={busy} onClick={() => void send(x, ["sent", "partial", "overdue"].includes(x.status))}><Send size={13} />{["sent", "partial", "overdue"].includes(x.status) ? "Resend" : "Send"}</button> : null}{!["paid", "cancelled", "credited"].includes(x.status) ? <button className="btn-secondary" disabled={busy} onClick={() => void cancel(x)}><XCircle size={13} />Cancel</button> : null}<button className="btn-secondary" disabled={busy} onClick={() => void remove(x)}><Trash2 size={13} />Delete</button></div></td></tr>)}{!items.length ? <tr><td colSpan={9} className="p-8 text-center text-[var(--admin-muted)]">No invoices match this view.</td></tr> : null}</tbody></table></div>
      </section>
    </div>}
  </ControlShell>;
}
