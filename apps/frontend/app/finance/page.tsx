"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Download, FileText, MailCheck, PauseCircle, PlayCircle, Send, Trash2, WalletCards } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Invoice = {
  id: string;
  invoice_number: string;
  client_name: string;
  recipient_email: string;
  description: string;
  quantity: number;
  rate_minor: number;
  tax_minor: number;
  subtotal_minor: number;
  total_minor: number;
  currency: string;
  due_date: string;
  status: string;
  email_subject: string;
  email_body: string;
  sent_at?: string | null;
  last_error?: string | null;
  created_at?: string | null;
};

type Schedule = {
  id: string;
  client_name: string;
  recipient_email: string;
  client_address: string;
  description: string;
  details: string;
  quantity: number;
  rate_minor: number;
  tax_minor: number;
  currency: string;
  send_day: number;
  due_days: number;
  enabled: boolean;
  last_sent_period?: string | null;
  last_error?: string | null;
};

type FormState = {
  client_name: string;
  recipient_email: string;
  client_address: string;
  description: string;
  details: string;
  service_period: string;
  quantity: string;
  rate: string;
  tax: string;
  due_date: string;
  email_subject: string;
  email_body: string;
};

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function isoDate(daysFromNow = 7) {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  return d.toISOString().slice(0, 10);
}

const initialForm: FormState = {
  client_name: "",
  recipient_email: "",
  client_address: "Maseru, Lesotho",
  description: "iMail Professional Business Email Service",
  details: "Monthly managed iMail service and business mailbox access",
  service_period: "",
  quantity: "1",
  rate: "185.00",
  tax: "0.00",
  due_date: isoDate(7),
  email_subject: "",
  email_body: "",
};

export default function FinancePage() {
  const [email, setEmail] = useState("");
  const [owner, setOwner] = useState(false);
  const [form, setForm] = useState<FormState>(initialForm);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [sendDay, setSendDay] = useState(String(new Date().getDate()));
  const [dueDays, setDueDays] = useState("7");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const quantity = Math.max(1, Number(form.quantity) || 1);
  const rate = Math.max(0, Number(form.rate) || 0);
  const tax = Math.max(0, Number(form.tax) || 0);
  const subtotal = quantity * rate;
  const total = subtotal + tax;

  const autoSubject = useMemo(() => `Ithute Invoice - ${form.client_name.trim() || "Client"}`, [form.client_name]);
  const autoBody = useMemo(() => {
    const name = form.client_name.trim() || "Client";
    const due = form.due_date ? new Date(`${form.due_date}T00:00:00`).toLocaleDateString(undefined, { day: "2-digit", month: "long", year: "numeric" }) : "the stated due date";
    return `Dear ${name},\n\nPlease find attached your invoice from Ithute Digital Solutions for ${form.description}.\n\nAmount due: M ${total.toFixed(2)}\nDue date: ${due}\n\nPayment details:\nBank: LPB\nAccount Name: Koetlisi Theko\nAccount Number: 1035927000011\n\nThe final email will automatically include the generated invoice number as the payment reference.\n\nKind regards,\nKoetlisi Theko Mofoka\nCEO, Ithute Digital Solutions`;
  }, [form.client_name, form.description, form.due_date, total]);

  useEffect(() => {
    void (async () => {
      const me = await api("/auth/me");
      if (!me.ok) return;
      const body = await me.json();
      setEmail(body.email || "");
      setOwner(Boolean(body.is_platform_owner));
      if (body.is_platform_owner) await loadFinance();
    })();
  }, []);

  async function loadFinance() {
    const [invoiceResponse, scheduleResponse] = await Promise.all([api("/finance/invoices"), api("/finance/schedules")]);
    if (invoiceResponse.ok) setInvoices((await invoiceResponse.json()).items || []);
    if (scheduleResponse.ok) setSchedules((await scheduleResponse.json()).items || []);
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function invoicePayload() {
    return {
      client_name: form.client_name.trim(), recipient_email: form.recipient_email.trim(), client_address: form.client_address.trim(),
      description: form.description.trim(), details: form.details.trim(), service_period: form.service_period.trim(), quantity,
      rate_minor: Math.round(rate * 100), tax_minor: Math.round(tax * 100), currency: "LSL", due_date: form.due_date,
      email_subject: form.email_subject.trim() || null, email_body: form.email_body.trim() || null,
    };
  }

  function validBaseFields() {
    if (!form.client_name.trim() || !form.recipient_email.trim() || !form.description.trim()) {
      setMessage("Client name, receiving email and description are required.");
      return false;
    }
    return true;
  }

  async function createInvoice(sendNow: boolean) {
    if (!validBaseFields() || !form.due_date) return;
    setBusy(true); setMessage("");
    try {
      const r = await api("/finance/invoices", { method: "POST", body: JSON.stringify(invoicePayload()) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "Unable to create invoice"));
      let invoice = data as Invoice;
      if (sendNow) {
        const s = await api(`/finance/invoices/${invoice.id}/send`, { method: "POST", body: JSON.stringify({ resend: false }) });
        const sent = await s.json().catch(() => ({}));
        if (!s.ok) throw new Error(`Invoice ${invoice.invoice_number} was created but email failed: ${String(sent.detail || "send failed")}`);
        invoice = sent as Invoice;
        setMessage(`Invoice ${invoice.invoice_number} generated and sent to ${invoice.recipient_email}.`);
      } else setMessage(`Invoice ${invoice.invoice_number} generated. Review the PDF, then send when ready.`);
      await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Finance operation failed"); }
    finally { setBusy(false); }
  }

  async function saveMonthlySchedule() {
    if (!validBaseFields()) return;
    const day = Number(sendDay); const due = Number(dueDays);
    if (!Number.isInteger(day) || day < 1 || day > 31 || !Number.isInteger(due) || due < 0 || due > 365) {
      setMessage("Monthly send day must be 1-31 and payment due days must be 0-365."); return;
    }
    if (!window.confirm(`Automatically generate and send this invoice to ${form.recipient_email} on day ${day} of every month?`)) return;
    setBusy(true); setMessage("");
    try {
      const r = await api("/finance/schedules", { method: "POST", body: JSON.stringify({
        client_name: form.client_name.trim(), recipient_email: form.recipient_email.trim(), client_address: form.client_address.trim(),
        description: form.description.trim(), details: form.details.trim(), quantity, rate_minor: Math.round(rate * 100),
        tax_minor: Math.round(tax * 100), currency: "LSL", send_day: day, due_days: due,
      }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "Unable to save monthly automation"));
      setMessage(`Monthly automatic invoice saved for ${form.client_name.trim()} — send day ${day}.`);
      await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save monthly automation"); }
    finally { setBusy(false); }
  }

  async function sendExisting(invoice: Invoice, resend = false) {
    if (!window.confirm(`${resend ? "Resend" : "Send"} ${invoice.invoice_number} to ${invoice.recipient_email}?`)) return;
    setBusy(true); setMessage("");
    try {
      const r = await api(`/finance/invoices/${invoice.id}/send`, { method: "POST", body: JSON.stringify({ resend }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "Unable to send invoice"));
      setMessage(`Invoice ${invoice.invoice_number} ${resend ? "resent" : "sent"} to ${invoice.recipient_email}.`);
      await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to send invoice"); }
    finally { setBusy(false); }
  }

  async function deleteInvoice(invoice: Invoice) {
    if (!window.confirm(`Delete ${invoice.invoice_number} for ${invoice.client_name}? This cannot be undone.`)) return;
    setBusy(true); setMessage("");
    try {
      const r = await api(`/finance/invoices/${invoice.id}`, { method: "DELETE" });
      if (!r.ok) { const data = await r.json().catch(() => ({})); throw new Error(String(data.detail || "Unable to delete invoice")); }
      setMessage(`Invoice ${invoice.invoice_number} deleted.`); await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to delete invoice"); }
    finally { setBusy(false); }
  }

  async function toggleSchedule(schedule: Schedule) {
    setBusy(true); setMessage("");
    try {
      const r = await api(`/finance/schedules/${schedule.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !schedule.enabled }) });
      if (!r.ok) { const data = await r.json().catch(() => ({})); throw new Error(String(data.detail || "Unable to update schedule")); }
      setMessage(`${schedule.client_name} monthly automation ${schedule.enabled ? "paused" : "enabled"}.`); await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to update schedule"); }
    finally { setBusy(false); }
  }

  async function deleteSchedule(schedule: Schedule) {
    if (!window.confirm(`Delete the monthly automatic invoice for ${schedule.client_name}?`)) return;
    setBusy(true); setMessage("");
    try {
      const r = await api(`/finance/schedules/${schedule.id}`, { method: "DELETE" });
      if (!r.ok) { const data = await r.json().catch(() => ({})); throw new Error(String(data.detail || "Unable to delete schedule")); }
      setMessage(`Monthly automation for ${schedule.client_name} deleted.`); await loadFinance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to delete schedule"); }
    finally { setBusy(false); }
  }

  async function downloadPdf(invoice: Invoice) {
    const r = await fetch(`${API}/finance/invoices/${invoice.id}/pdf`, { credentials: "include" });
    if (!r.ok) { const data = await r.json().catch(() => ({})); setMessage(String(data.detail || "Unable to download PDF")); return; }
    const blob = await r.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `${invoice.invoice_number}.pdf`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }

  const money = (minor: number) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <ControlShell title="Finance & invoices" subtitle="Create, review and send branded Ithute invoices" userEmail={email}>
      {!owner ? <section className="surface-card p-6"><h1 className="text-xl font-black">Finance is restricted</h1><p className="mt-2 text-sm text-[var(--admin-muted)]">Only the Ithute platform owner can manage company invoices.</p></section> : (
        <div className="space-y-4">
          <section className="surface-card overflow-hidden">
            <div className="border-b bg-gradient-to-r from-[#f7fbff] via-white to-[#f5fbf2] p-5">
              <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="eyebrow-label">Ithute internal finance</p><h1 className="mt-2 text-2xl font-black">New invoice</h1><p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--admin-muted)]">Create one invoice now, or use the same client and service details to schedule automatic monthly generation and sending from invoices@ithute.co.ls.</p></div><div className="rounded-2xl border bg-white px-4 py-3 text-right shadow-sm"><p className="text-[9px] font-black uppercase tracking-[.16em] text-[var(--admin-muted)]">Live total</p><p className="mt-1 text-2xl font-black text-[#0b5b39]">M {total.toFixed(2)}</p></div></div>
            </div>
            <div className="grid gap-5 p-5 xl:grid-cols-[1.15fr_.85fr]">
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2"><label className="text-xs font-bold">Client / company name<input className="input mt-1" value={form.client_name} onChange={(e) => update("client_name", e.target.value)} placeholder="e.g. ABC Holdings (Pty) Ltd" /></label><label className="text-xs font-bold">Receiving email<input className="input mt-1" type="email" value={form.recipient_email} onChange={(e) => update("recipient_email", e.target.value)} placeholder="accounts@client.co.ls" /></label></div>
                <label className="text-xs font-bold">Client address<input className="input mt-1" value={form.client_address} onChange={(e) => update("client_address", e.target.value)} /></label>
                <label className="text-xs font-bold">Service / invoice description<input className="input mt-1" value={form.description} onChange={(e) => update("description", e.target.value)} /></label>
                <label className="text-xs font-bold">Supporting detail<input className="input mt-1" value={form.details} onChange={(e) => update("details", e.target.value)} /></label>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><label className="text-xs font-bold">Service period<input className="input mt-1" value={form.service_period} onChange={(e) => update("service_period", e.target.value)} placeholder="September 2026" /></label><label className="text-xs font-bold">Quantity<input className="input mt-1" type="number" min="1" value={form.quantity} onChange={(e) => update("quantity", e.target.value)} /></label><label className="text-xs font-bold">Rate (M)<input className="input mt-1" type="number" min="0" step="0.01" value={form.rate} onChange={(e) => update("rate", e.target.value)} /></label><label className="text-xs font-bold">Tax (M)<input className="input mt-1" type="number" min="0" step="0.01" value={form.tax} onChange={(e) => update("tax", e.target.value)} /></label></div>
                <label className="text-xs font-bold">Payment due date<input className="input mt-1 max-w-xs" type="date" value={form.due_date} onChange={(e) => update("due_date", e.target.value)} /></label>
                <details className="rounded-2xl border bg-[#fafcfb] p-4"><summary className="cursor-pointer text-xs font-black">Optional email override</summary><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Leave blank to use the automatic professional email.</p><label className="mt-3 block text-xs font-bold">Subject<input className="input mt-1" value={form.email_subject} onChange={(e) => update("email_subject", e.target.value)} placeholder={autoSubject} /></label><label className="mt-3 block text-xs font-bold">Email body<textarea className="input mt-1 min-h-40 resize-y" value={form.email_body} onChange={(e) => update("email_body", e.target.value)} placeholder={autoBody} /></label></details>
                <div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={busy} onClick={() => void createInvoice(false)}><FileText size={15} />Generate invoice</button><button className="btn-primary" disabled={busy} onClick={() => { if (window.confirm(`Generate the invoice and send it to ${form.recipient_email || "the receiving email"}?`)) void createInvoice(true); }}><Send size={15} />Generate PDF & send</button></div>
                <div className="rounded-2xl border border-[#cbdde9] bg-[#f8fbfd] p-4">
                  <div className="flex items-center gap-2"><CalendarClock size={18} className="text-[#075135]" /><div><p className="text-sm font-black">Monthly automatic invoice</p><p className="text-[10px] text-[var(--admin-muted)]">Uses the client, service and amount entered above. The service period is updated automatically each month.</p></div></div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs font-bold">Generate & send on day<input className="input mt-1" type="number" min="1" max="31" value={sendDay} onChange={(e) => setSendDay(e.target.value)} /></label><label className="text-xs font-bold">Payment due after (days)<input className="input mt-1" type="number" min="0" max="365" value={dueDays} onChange={(e) => setDueDays(e.target.value)} /></label></div>
                  <button className="btn-primary mt-3" disabled={busy} onClick={() => void saveMonthlySchedule()}><CalendarClock size={15} />Save monthly auto-send</button>
                </div>
              </div>
              <aside className="rounded-[26px] border border-[#cbdde9] bg-white p-5 shadow-[0_18px_40px_rgba(12,58,86,.07)]">
                <div className="flex items-center justify-between gap-3 border-b pb-4"><div className="flex items-center gap-3"><img src="/brand/ids-mark.svg" alt="Ithute" className="h-12 w-12" /><div><p className="text-lg font-black text-[#082b58]">Ithute</p><p className="text-[9px] font-black uppercase tracking-[.18em] text-[#087743]">Solutions</p></div></div><img src="/brand/imail-logo.webp" alt="iMail" className="h-11 w-auto object-contain" /></div>
                <div className="py-5"><div className="flex items-start justify-between gap-3"><div><p className="text-3xl font-black text-[#082b58]">INVOICE</p><div className="mt-2 h-0.5 w-32 bg-gradient-to-r from-[#087743] to-[#d5a62f]" /></div><div className="rounded-xl bg-[#f2f7fb] px-3 py-2 text-right text-[9px]"><p className="font-black">Invoice No.</p><p className="text-[var(--admin-muted)]">Auto-generated</p></div></div><div className="mt-5"><p className="text-[9px] font-black uppercase text-[#082b58]">Billed to</p><p className="mt-1 font-black">{form.client_name || "Client name"}</p><p className="text-xs text-[var(--admin-muted)]">{form.recipient_email || "receiving@email"}</p></div><div className="mt-5 overflow-hidden rounded-xl border"><div className="grid grid-cols-[1fr_auto] bg-[#f2f7fb] px-3 py-2 text-[9px] font-black text-[#082b58]"><span>Description</span><span>Amount</span></div><div className="grid grid-cols-[1fr_auto] gap-3 px-3 py-3 text-xs"><div><p className="font-bold">{form.description}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{form.details}</p></div><p className="font-black">M {subtotal.toFixed(2)}</p></div></div><div className="mt-3 ml-auto w-56 rounded-xl bg-[#f1f9eb] px-4 py-3"><div className="flex justify-between text-xs font-black text-[#075135]"><span>TOTAL DUE</span><span>M {total.toFixed(2)}</span></div></div><div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2"><div className="rounded-xl border p-3 text-[10px]"><p className="font-black text-[#082b58]">PAYMENT DETAILS</p><p className="mt-2">LPB · Koetlisi Theko</p><p>1035927000011</p></div><div className="rounded-xl border p-3 text-[10px]"><p className="font-black text-[#082b58]">SENDING FROM</p><p className="mt-2">invoices@ithute.co.ls</p><p>PDF attached automatically</p></div></div><div className="mt-5 border-t pt-4"><p className="font-serif text-2xl italic text-[#24364c]">Koetlisi Theko Mofoka</p><p className="mt-1 text-[10px] font-black">Koetlisi Theko Mofoka</p><p className="text-[9px] text-[var(--admin-muted)]">CEO, Ithute Digital Solutions</p></div></div>
              </aside>
            </div>
          </section>

          {message ? <div className="surface-card p-3 text-xs font-bold">{message}</div> : null}

          <section className="surface-card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><p className="eyebrow-label">Automatic billing</p><h2 className="mt-1 font-black">Monthly invoice schedules</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Invoices are generated and sent automatically on the chosen day. Day 29-31 is clamped to the last day in shorter months.</p></div><div className="rounded-xl bg-[#eef6f2] px-3 py-2 text-xs font-black text-[#285b55]">{schedules.filter((x) => x.enabled).length} active</div></div>
            <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Client</th><th className="p-3">Recipient</th><th className="p-3">Amount</th><th className="p-3">Send day</th><th className="p-3">Due after</th><th className="p-3">Last sent</th><th className="p-3">Actions</th></tr></thead><tbody>{schedules.map((s) => <tr key={s.id} className="border-t align-top"><td className="p-3 font-bold">{s.client_name}<div className="mt-1 text-[9px] font-normal text-[var(--admin-muted)]">{s.description}</div></td><td className="p-3 text-[var(--admin-muted)]">{s.recipient_email}</td><td className="p-3 font-black">{money(s.quantity * s.rate_minor + s.tax_minor)}</td><td className="p-3">Day {s.send_day}</td><td className="p-3">{s.due_days} days</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${s.enabled ? "bg-[#e9f7ee] text-[#146b3a]" : "bg-[#eef3f7] text-[#526474]"}`}>{s.enabled ? "active" : "paused"}</span><p className="mt-2 text-[10px]">{s.last_sent_period || "Not yet"}</p>{s.last_error ? <p className="mt-1 max-w-xs text-[9px] text-[#a43a34]">{s.last_error}</p> : null}</td><td className="p-3"><div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={busy} onClick={() => void toggleSchedule(s)}>{s.enabled ? <PauseCircle size={13} /> : <PlayCircle size={13} />}{s.enabled ? "Pause" : "Enable"}</button><button className="btn-secondary" disabled={busy} onClick={() => void deleteSchedule(s)}><Trash2 size={13} />Delete</button></div></td></tr>)}{!schedules.length ? <tr><td colSpan={7} className="p-8 text-center text-[var(--admin-muted)]">No monthly invoice schedules yet.</td></tr> : null}</tbody></table></div>
          </section>

          <section className="surface-card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><p className="eyebrow-label">Finance register</p><h2 className="mt-1 font-black">Invoices</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Draft, sent and failed invoice deliveries remain visible here until you explicitly delete them.</p></div><div className="flex items-center gap-2 rounded-xl bg-[#eef6f2] px-3 py-2 text-xs font-black text-[#285b55]"><WalletCards size={15} />{invoices.length} invoices</div></div>
            <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Invoice</th><th className="p-3">Client</th><th className="p-3">Recipient</th><th className="p-3">Amount</th><th className="p-3">Due</th><th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead><tbody>{invoices.map((x) => <tr key={x.id} className="border-t align-top"><td className="p-3 font-mono font-bold">{x.invoice_number}</td><td className="p-3 font-bold">{x.client_name}</td><td className="p-3 text-[var(--admin-muted)]">{x.recipient_email}</td><td className="p-3 font-black">{money(x.total_minor)}</td><td className="p-3">{new Date(`${x.due_date}T00:00:00`).toLocaleDateString()}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${x.status === "sent" ? "bg-[#e9f7ee] text-[#146b3a]" : x.status === "failed" ? "bg-[#fff0ef] text-[#a43a34]" : "bg-[#eef3f7] text-[#526474]"}`}>{x.status}</span>{x.last_error ? <p className="mt-2 max-w-xs text-[9px] text-[#a43a34]">{x.last_error}</p> : null}</td><td className="p-3"><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => void downloadPdf(x)}><Download size={13} />PDF</button>{x.status === "sent" ? <button className="btn-secondary" disabled={busy} onClick={() => void sendExisting(x, true)}><MailCheck size={13} />Resend</button> : <button className="btn-primary" disabled={busy} onClick={() => void sendExisting(x, false)}><Send size={13} />Send</button>}<button className="btn-secondary" disabled={busy} onClick={() => void deleteInvoice(x)}><Trash2 size={13} />Delete</button></div></td></tr>)}{!invoices.length ? <tr><td colSpan={7} className="p-8 text-center text-[var(--admin-muted)]">No finance invoices yet.</td></tr> : null}</tbody></table></div>
          </section>
        </div>
      )}
    </ControlShell>
  );
}
