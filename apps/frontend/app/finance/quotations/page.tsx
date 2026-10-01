"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, FilePlus2, Mail, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Quote = {
  id: string; document_number: string; client_name: string; recipient_emails: string[]; status: string;
  mailbox_count: number; storage_gb: number; monthly_total_minor: number; quarterly_total_minor: number;
  annual_total_minor: number; created_at?: string | null; sent_at?: string | null;
};

const toMinor = (value: string) => Math.round(Math.max(0, Number(value) || 0) * 100);
const fromMinor = (value: number) => (value / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function CorporateQuotationsPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [clientName, setClientName] = useState("");
  const [recipients, setRecipients] = useState("");
  const [address, setAddress] = useState("Maseru, Lesotho");
  const [mailboxes, setMailboxes] = useState("20");
  const [storage, setStorage] = useState("50");
  const [retail, setRetail] = useState("400");
  const [monthly, setMonthly] = useState("7000");
  const [quarterly, setQuarterly] = useState("19500");
  const [annual, setAnnual] = useState("72000");
  const [validity, setValidity] = useState("30");
  const [preparedBy, setPreparedBy] = useState("Koetlisi Theko");
  const [preparedEmail, setPreparedEmail] = useState("thekoetlisi@ithute.co.ls");
  const [preparedPhone, setPreparedPhone] = useState("+266 5900 1394");
  const [notes, setNotes] = useState("");

  const totalGb = useMemo(() => Math.max(1, Number(mailboxes) || 1) * Math.max(1, Number(storage) || 1), [mailboxes, storage]);
  const perAnnualMonth = useMemo(() => Math.max(0, Number(annual) || 0) / 12 / Math.max(1, Number(mailboxes) || 1), [annual, mailboxes]);

  useEffect(() => { void init(); }, []);

  async function init() {
    const me = await fetch(`${API}/auth/me`, { credentials: "include" });
    if (me.status === 401) { router.replace("/login"); return; }
    const data = me.ok ? await me.json() : {};
    setEmail(data.email || "");
    if (!data.is_platform_owner) { setLoading(false); return; }
    setAllowed(true); await load(); setLoading(false);
  }
  async function load() {
    const r = await fetch(`${API}/finance/corporate-quotations`, { credentials: "include" });
    if (r.ok) setQuotes((await r.json()).items || []);
  }
  function parsedRecipients() {
    return recipients.split(/[;,\n]+/).map((x) => x.trim()).filter(Boolean);
  }
  async function createQuote() {
    const emails = parsedRecipients();
    if (!clientName.trim() || !emails.length) return setMessage("Client name and at least one receiving email are required.");
    setBusy(true); setMessage("");
    try {
      const r = await fetch(`${API}/finance/corporate-quotations`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_name: clientName.trim(), recipient_emails: emails, client_address: address.trim(),
          mailbox_count: Math.max(1, Number(mailboxes) || 1), storage_gb: Math.max(1, Number(storage) || 1),
          retail_per_mailbox_minor: toMinor(retail), monthly_total_minor: toMinor(monthly),
          quarterly_total_minor: toMinor(quarterly), annual_total_minor: toMinor(annual),
          validity_days: Math.max(1, Number(validity) || 30), notes: notes.trim(), prepared_by: preparedBy.trim(),
          prepared_email: preparedEmail.trim(), prepared_phone: preparedPhone.trim(),
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(data.detail || "Unable to create quotation"));
      setMessage(`${data.document_number} created. You can download the PDF or send it directly.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to create quotation"); }
    finally { setBusy(false); }
  }
  async function download(row: Quote) {
    const r = await fetch(`${API}/finance/corporate-quotations/${row.id}/pdf`, { credentials: "include" });
    if (!r.ok) return setMessage("Unable to generate quotation PDF.");
    const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = `${row.document_number}.pdf`; a.click(); URL.revokeObjectURL(url);
  }
  async function send(row: Quote) {
    if (!window.confirm(`Send ${row.document_number} to ${row.recipient_emails.join(", ")}?`)) return;
    setBusy(true); setMessage("");
    try {
      const r = await fetch(`${API}/finance/corporate-quotations/${row.id}/send`, { method: "POST", credentials: "include" });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to send quotation"));
      setMessage(`${row.document_number} sent successfully.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to send quotation"); }
    finally { setBusy(false); }
  }

  return <ControlShell title="Corporate quotations" subtitle="Generate detailed Ithute / iMail sales quotations" userEmail={email}>
    {loading ? <section className="surface-card p-6">Loading quotation workspace…</section> : !allowed ? <section className="surface-card p-6 text-sm font-bold text-red-700">Platform-owner access is required.</section> : <div className="space-y-4">
      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-5">
          <div><p className="eyebrow-label">Sales document</p><h1 className="mt-1 text-2xl font-black">iMail Corporate Email Quotation</h1><p className="mt-1 text-xs text-[var(--admin-muted)]">Creates the detailed two-page branded quotation with pricing options, migration plan, terms and direct email delivery.</p></div>
          <div className="rounded-2xl bg-[#eef6f2] px-5 py-3 text-right"><p className="text-[9px] font-black uppercase">Allocated storage</p><p className="text-2xl font-black text-[#075135]">{totalGb >= 1000 ? `${(totalGb/1000).toFixed(totalGb%1000?1:0)} TB` : `${totalGb} GB`}</p><p className="text-[10px] text-[#718078]">Annual: M {Number(annual || 0).toLocaleString()}</p></div>
        </div>
        <div className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-2"><label className="text-xs font-bold">Client / company<input className="input mt-1" value={clientName} onChange={(e)=>setClientName(e.target.value)} placeholder="Global IT" /></label><label className="text-xs font-bold">Receiving emails <span className="font-normal text-[var(--admin-muted)]">(comma separated)</span><textarea className="input mt-1 min-h-20" value={recipients} onChange={(e)=>setRecipients(e.target.value)} placeholder="accounts@example.co.ls, support@example.co.ls" /></label></div>
          <label className="text-xs font-bold">Client address<input className="input mt-1" value={address} onChange={(e)=>setAddress(e.target.value)} /></label>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label className="text-xs font-bold">Mailboxes<input className="input mt-1" type="number" min="1" value={mailboxes} onChange={(e)=>setMailboxes(e.target.value)} /></label><label className="text-xs font-bold">GB per mailbox<input className="input mt-1" type="number" min="1" value={storage} onChange={(e)=>setStorage(e.target.value)} /></label><label className="text-xs font-bold">Retail / mailbox / month (M)<input className="input mt-1" type="number" min="0" step="0.01" value={retail} onChange={(e)=>setRetail(e.target.value)} /></label><label className="text-xs font-bold">Validity (days)<input className="input mt-1" type="number" min="1" max="180" value={validity} onChange={(e)=>setValidity(e.target.value)} /></label></div>
          <div className="grid gap-3 md:grid-cols-3"><label className="text-xs font-bold">Monthly total (M)<input className="input mt-1" type="number" min="0" step="0.01" value={monthly} onChange={(e)=>setMonthly(e.target.value)} /></label><label className="text-xs font-bold">Quarterly total (M)<input className="input mt-1" type="number" min="0" step="0.01" value={quarterly} onChange={(e)=>setQuarterly(e.target.value)} /></label><label className="text-xs font-bold">Annual total (M)<input className="input mt-1" type="number" min="0" step="0.01" value={annual} onChange={(e)=>setAnnual(e.target.value)} /></label></div>
          <div className="rounded-2xl bg-[#f7faf8] p-4 text-xs"><p className="font-black">Calculated annual package</p><p className="mt-1 text-[var(--admin-muted)]">M {Number(annual || 0).toLocaleString()} / year = M {(Number(annual || 0)/12).toLocaleString(undefined,{maximumFractionDigits:2})} / month = M {perAnnualMonth.toLocaleString(undefined,{maximumFractionDigits:2})} per mailbox / month.</p></div>
          <div className="grid gap-3 md:grid-cols-3"><label className="text-xs font-bold">Prepared by<input className="input mt-1" value={preparedBy} onChange={(e)=>setPreparedBy(e.target.value)} /></label><label className="text-xs font-bold">Prepared by email<input className="input mt-1" type="email" value={preparedEmail} onChange={(e)=>setPreparedEmail(e.target.value)} /></label><label className="text-xs font-bold">Telephone<input className="input mt-1" value={preparedPhone} onChange={(e)=>setPreparedPhone(e.target.value)} /></label></div>
          <label className="text-xs font-bold">Optional internal / client note<textarea className="input mt-1 min-h-20" value={notes} onChange={(e)=>setNotes(e.target.value)} /></label>
          <button className="btn-primary" disabled={busy} onClick={()=>void createQuote()}><FilePlus2 size={15}/>Generate quotation</button>
        </div>
      </section>
      {message ? <div className="surface-card p-3 text-xs font-bold">{message}</div> : null}
      <section className="surface-card overflow-hidden"><div className="flex items-center justify-between border-b p-4"><div><p className="eyebrow-label">Quotation register</p><h2 className="mt-1 font-black">Corporate iMail quotations</h2></div><span className="rounded-xl bg-[#eef6f2] px-3 py-2 text-xs font-black">{quotes.length}</span></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Quotation</th><th className="p-3">Client</th><th className="p-3">Package</th><th className="p-3">Annual</th><th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead><tbody>{quotes.map((row)=><tr key={row.id} className="border-t align-top"><td className="p-3 font-mono font-bold">{row.document_number}</td><td className="p-3"><p className="font-bold">{row.client_name}</p><p className="mt-1 max-w-64 text-[10px] text-[var(--admin-muted)]">{row.recipient_emails.join(", ")}</p></td><td className="p-3">{row.mailbox_count} × {row.storage_gb} GB</td><td className="p-3 font-black">M {fromMinor(row.annual_total_minor)}</td><td className="p-3"><span className="rounded-full bg-[#eef3f7] px-2 py-1 text-[9px] font-black uppercase">{row.status}</span></td><td className="p-3"><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={()=>void download(row)}><Download size={13}/>PDF</button><button className="btn-primary" disabled={busy} onClick={()=>void send(row)}><Send size={13}/>Send</button></div></td></tr>)}{!quotes.length?<tr><td colSpan={6} className="p-8 text-center text-[var(--admin-muted)]"><Mail className="mx-auto mb-2"/>No corporate quotations yet.</td></tr>:null}</tbody></table></div></section>
    </div>}
  </ControlShell>;
}
