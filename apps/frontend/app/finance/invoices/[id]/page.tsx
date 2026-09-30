"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, History, Save, Send } from "lucide-react";
import Link from "next/link";
import { ControlShell } from "@/components/control-shell";
import { financeRoleRank, useFinanceAccess } from "../../_components/use-finance-access";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Line = { id?: string; description: string; details: string; quantity: number; rate_minor: number; tax_minor: number; total_minor?: number };
type Payment = { id: string; amount_minor: number; payment_date: string; method: string; reference: string; created_at?: string };
type Credit = { id: string; credit_number: string; amount_minor: number; reason: string; created_at?: string };
type Invoice = {
  id: string; invoice_number: string; client_name: string; recipient_email: string; client_address: string; description: string; details: string;
  service_period: string; quantity: number; rate_minor: number; tax_minor: number; subtotal_minor: number; total_minor: number;
  paid_minor: number; credited_minor: number; adjusted_total_minor: number; outstanding_minor: number; due_date: string; status: string;
  email_subject: string; email_body: string; sent_at?: string | null; created_at?: string; items: Line[]; payments: Payment[]; credit_notes: Credit[];
};
type Activity = { id: string; action: string; created_at?: string; metadata: Record<string, unknown> };

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
}
const money = (minor = 0) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function InvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { email, allowed, role, loading: accessLoading } = useFinanceAccess();
  const canWrite = financeRoleRank(role) >= 2;
  const [invoice, setInvoice] = useState<Invoice | null>(null); const [activity, setActivity] = useState<Activity[]>([]); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  const editable = canWrite && invoice ? ["draft", "failed"].includes(invoice.status) && !invoice.sent_at && invoice.payments.length === 0 && invoice.credit_notes.length === 0 && invoice.items.length <= 1 : false;

  const [clientName, setClientName] = useState(""); const [recipientEmail, setRecipientEmail] = useState(""); const [address, setAddress] = useState(""); const [description, setDescription] = useState(""); const [details, setDetails] = useState(""); const [period, setPeriod] = useState(""); const [qty, setQty] = useState("1"); const [rate, setRate] = useState("0.00"); const [tax, setTax] = useState("0.00"); const [due, setDue] = useState("");

  async function load() {
    const [a, b] = await Promise.all([api(`/finance/invoices/${id}`), api(`/finance/invoices/${id}/activity`)]);
    if (a.ok) {
      const row: Invoice = await a.json(); setInvoice(row); setClientName(row.client_name); setRecipientEmail(row.recipient_email); setAddress(row.client_address || ""); setDescription(row.description); setDetails(row.details || ""); setPeriod(row.service_period || ""); setQty(String(row.quantity)); setRate((row.rate_minor / 100).toFixed(2)); setTax((row.tax_minor / 100).toFixed(2)); setDue(row.due_date);
    }
    if (b.ok) setActivity((await b.json()).items || []);
  }

  useEffect(() => { if (allowed) void load(); }, [id, allowed]);

  async function save() {
    if (!canWrite) return setMessage("Finance Clerk access is required to edit invoices.");
    if (!invoice) return; setBusy(true); setMessage("");
    try {
      const r = await api(`/finance/invoices/${invoice.id}`, { method: "PUT", body: JSON.stringify({ client_name: clientName, recipient_email: recipientEmail, client_address: address, description, details, service_period: period, quantity: Math.max(1, Number(qty) || 1), rate_minor: Math.round(Math.max(0, Number(rate) || 0) * 100), tax_minor: Math.round(Math.max(0, Number(tax) || 0) * 100), due_date: due, email_subject: null, email_body: null }) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to update invoice")); setMessage("Draft invoice updated."); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to update invoice"); } finally { setBusy(false); }
  }

  async function pdf() { if (!invoice) return; const r = await fetch(`${API}/finance/invoices/${invoice.id}/pdf`, { credentials: "include" }); if (!r.ok) return; const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `${invoice.invoice_number}.pdf`; a.click(); URL.revokeObjectURL(url); }
  async function send() { if (!canWrite) return setMessage("Finance Clerk access is required to send invoices."); if (!invoice) return; setBusy(true); try { const r = await api(`/finance/invoices/${invoice.id}/send`, { method: "POST", body: JSON.stringify({ resend: ["sent", "partial", "overdue"].includes(invoice.status) }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to send invoice")); setMessage("Invoice sent."); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to send invoice"); } finally { setBusy(false); } }

  const headline = useMemo(() => invoice ? `${invoice.invoice_number} · ${invoice.client_name}` : "Invoice detail", [invoice]);

  return <ControlShell title="Invoice detail" subtitle={headline} userEmail={email}>
    {accessLoading ? <section className="surface-card p-6">Checking Finance access…</section> : !allowed ? <section className="surface-card p-6">Finance access is required.</section> : !invoice ? <section className="surface-card p-6">Loading invoice…</section> : <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><Link href="/finance/collections" className="btn-secondary"><ArrowLeft size={14} />Collections</Link><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => void pdf()}><Download size={14} />PDF</button>{canWrite && !["paid", "cancelled", "credited"].includes(invoice.status) ? <button className="btn-secondary" disabled={busy} onClick={() => void send()}><Send size={14} />{invoice.sent_at ? "Resend" : "Send"}</button> : null}</div></div>
      {message ? <div className="surface-card p-3 text-xs font-bold">{message}</div> : null}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Status</p><p className="mt-2 text-lg font-black uppercase">{invoice.status}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Invoice total</p><p className="mt-2 text-lg font-black">{money(invoice.total_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Paid</p><p className="mt-2 text-lg font-black">{money(invoice.paid_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Credits</p><p className="mt-2 text-lg font-black">{money(invoice.credited_minor)}</p></div>
        <div className="surface-card p-4"><p className="text-[10px] font-black uppercase">Outstanding</p><p className="mt-2 text-lg font-black">{money(invoice.outstanding_minor)}</p></div>
      </section>

      <section className="surface-card p-5"><div className="mb-4 flex items-center justify-between"><div><p className="eyebrow-label">Invoice record</p><h2 className="mt-1 text-lg font-black">{editable ? "Edit draft invoice" : "Locked / read-only financial document"}</h2></div>{editable ? <button className="btn-primary" disabled={busy} onClick={() => void save()}><Save size={14} />Save changes</button> : <span className="rounded-full bg-[#eef3f7] px-3 py-1 text-[10px] font-black uppercase">{canWrite ? "Locked after sending" : "Read only"}</span>}</div>
        <div className="grid gap-3 md:grid-cols-2"><label className="text-xs font-bold">Client<input className="input mt-1" disabled={!editable} value={clientName} onChange={(e) => setClientName(e.target.value)} /></label><label className="text-xs font-bold">Email<input className="input mt-1" disabled={!editable} value={recipientEmail} onChange={(e) => setRecipientEmail(e.target.value)} /></label><label className="text-xs font-bold md:col-span-2">Address<input className="input mt-1" disabled={!editable} value={address} onChange={(e) => setAddress(e.target.value)} /></label><label className="text-xs font-bold md:col-span-2">Description<input className="input mt-1" disabled={!editable} value={description} onChange={(e) => setDescription(e.target.value)} /></label><label className="text-xs font-bold md:col-span-2">Supporting detail<input className="input mt-1" disabled={!editable} value={details} onChange={(e) => setDetails(e.target.value)} /></label><label className="text-xs font-bold">Service period<input className="input mt-1" disabled={!editable} value={period} onChange={(e) => setPeriod(e.target.value)} /></label><label className="text-xs font-bold">Due date<input className="input mt-1" type="date" disabled={!editable} value={due} onChange={(e) => setDue(e.target.value)} /></label><label className="text-xs font-bold">Quantity<input className="input mt-1" disabled={!editable} value={qty} onChange={(e) => setQty(e.target.value)} /></label><label className="text-xs font-bold">Rate (M)<input className="input mt-1" disabled={!editable} value={rate} onChange={(e) => setRate(e.target.value)} /></label><label className="text-xs font-bold">Tax (M)<input className="input mt-1" disabled={!editable} value={tax} onChange={(e) => setTax(e.target.value)} /></label></div>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <section className="surface-card overflow-hidden"><div className="border-b p-4"><h3 className="font-black">Line items</h3></div><div className="divide-y">{(invoice.items.length ? invoice.items : [{ description: invoice.description, details: invoice.details, quantity: invoice.quantity, rate_minor: invoice.rate_minor, tax_minor: invoice.tax_minor }]).map((x, i) => <div key={x.id || i} className="p-4 text-xs"><p className="font-black">{x.description}</p><p className="mt-1 text-[var(--admin-muted)]">{x.details}</p><p className="mt-2">{x.quantity} × {money(x.rate_minor)} · Tax {money(x.tax_minor)}</p></div>)}</div></section>
        <section className="surface-card overflow-hidden"><div className="border-b p-4"><h3 className="font-black">Payments & credits</h3></div><div className="divide-y">{invoice.payments.map((x) => <div key={x.id} className="p-4 text-xs"><p className="font-black">Payment {money(x.amount_minor)}</p><p>{x.payment_date} · {x.method}</p><p className="text-[var(--admin-muted)]">{x.reference}</p></div>)}{invoice.credit_notes.map((x) => <div key={x.id} className="p-4 text-xs"><p className="font-black">{x.credit_number} · {money(x.amount_minor)}</p><p className="text-[var(--admin-muted)]">{x.reason}</p></div>)}{!invoice.payments.length && !invoice.credit_notes.length ? <div className="p-4 text-xs text-[var(--admin-muted)]">No payments or credit notes yet.</div> : null}</div></section>
        <section className="surface-card overflow-hidden"><div className="flex items-center gap-2 border-b p-4"><History size={15} /><h3 className="font-black">Delivery & audit history</h3></div><div className="max-h-[420px] divide-y overflow-auto">{activity.map((x) => <div key={x.id} className="p-4 text-xs"><p className="font-black">{x.action.replaceAll("finance.", "").replaceAll(".", " ")}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{x.created_at ? new Date(x.created_at).toLocaleString() : ""}</p></div>)}{!activity.length ? <div className="p-4 text-xs text-[var(--admin-muted)]">No audit events recorded yet. New sends, edits and reminders will appear here.</div> : null}</div></section>
      </div>
    </div>}
  </ControlShell>;
}
