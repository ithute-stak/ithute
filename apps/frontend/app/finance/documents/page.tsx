"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Download, FileCheck2, FilePlus2, Mail, Plus, ReceiptText, Send, Trash2, XCircle } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Client = { id: string; name: string; email: string; address: string; payment_terms_days: number };
type Line = { description: string; details: string; quantity: string; rate: string; tax: string };
type DocumentRow = {
  id: string; document_number: string; document_type: "quotation" | "proforma"; status: string;
  client_name: string; recipient_email: string; total_minor: number; valid_until?: string | null;
  converted_invoice_id?: string | null; items: unknown[];
};

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
}

const blankLine = (): Line => ({ description: "", details: "", quantity: "1", rate: "0.00", tax: "0.00" });

export default function FinanceDocumentsPage() {
  const [email, setEmail] = useState("");
  const [owner, setOwner] = useState(false);
  const [clients, setClients] = useState<Client[]>([]);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [type, setType] = useState<"quotation" | "proforma">("quotation");
  const [clientId, setClientId] = useState("");
  const [clientName, setClientName] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [address, setAddress] = useState("Maseru, Lesotho");
  const [validUntil, setValidUntil] = useState("");
  const [terms, setTerms] = useState("7");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>([{ description: "iMail Professional Business Email Service", details: "Monthly managed iMail service and business mailbox access", quantity: "1", rate: "185.00", tax: "0.00" }]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const total = useMemo(() => lines.reduce((sum, line) => sum + (Math.max(1, Number(line.quantity) || 1) * Math.max(0, Number(line.rate) || 0)) + Math.max(0, Number(line.tax) || 0), 0), [lines]);

  useEffect(() => { void boot(); }, []);
  async function boot() {
    const me = await api("/auth/me"); if (!me.ok) return; const user = await me.json();
    setEmail(user.email || ""); setOwner(Boolean(user.is_platform_owner)); if (user.is_platform_owner) await load();
  }
  async function load() {
    const [c, d] = await Promise.all([api("/finance/clients?active=true"), api("/finance/documents")]);
    if (c.ok) setClients((await c.json()).items || []); if (d.ok) setDocuments((await d.json()).items || []);
  }
  function chooseClient(id: string) {
    setClientId(id); const c = clients.find((x) => x.id === id); if (!c) return;
    setClientName(c.name); setRecipientEmail(c.email); setAddress(c.address || "Maseru, Lesotho"); setTerms(String(c.payment_terms_days ?? 7));
  }
  function updateLine(index: number, key: keyof Line, value: string) { setLines((rows) => rows.map((row, i) => i === index ? { ...row, [key]: value } : row)); }
  function addLine() { if (lines.length < 8) setLines((rows) => [...rows, blankLine()]); }
  function removeLine(index: number) { if (lines.length > 1) setLines((rows) => rows.filter((_, i) => i !== index)); }
  function payload() {
    return {
      document_type: type, client_id: clientId || null, client_name: clientName.trim(), recipient_email: recipientEmail.trim(),
      client_address: address.trim(), currency: "LSL", valid_until: validUntil || null, payment_terms_days: Math.max(0, Number(terms) || 0), notes: notes.trim(),
      items: lines.map((line) => ({ description: line.description.trim(), details: line.details.trim(), quantity: Math.max(1, Number(line.quantity) || 1), rate_minor: Math.round(Math.max(0, Number(line.rate) || 0) * 100), tax_minor: Math.round(Math.max(0, Number(line.tax) || 0) * 100) })),
    };
  }
  async function create() {
    if (!clientName.trim() || !recipientEmail.trim() || lines.some((x) => !x.description.trim())) { setMessage("Client, receiving email and every line description are required."); return; }
    setBusy(true); setMessage("");
    try { const r = await api("/finance/documents", { method: "POST", body: JSON.stringify(payload()) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to create document")); setMessage(`${data.document_number} created.`); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Unable to create document"); } finally { setBusy(false); }
  }
  async function action(row: DocumentRow, path: string, body?: unknown) {
    setBusy(true); setMessage("");
    try { const r = await api(`/finance/documents/${row.id}/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Action failed")); setMessage(path === "convert" ? `${row.document_number} converted to ${data.invoice_number}.` : `${row.document_number} updated.`); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  }
  async function remove(row: DocumentRow) {
    if (!window.confirm(`Delete ${row.document_number}?`)) return; setBusy(true);
    try { const r = await api(`/finance/documents/${row.id}`, { method: "DELETE" }); if (!r.ok) { const data = await r.json().catch(() => ({})); throw new Error(String(data.detail || "Unable to delete")); } setMessage(`${row.document_number} deleted.`); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Unable to delete"); } finally { setBusy(false); }
  }
  async function pdf(row: DocumentRow) {
    const r = await fetch(`${API}/finance/documents/${row.id}/pdf`, { credentials: "include" }); if (!r.ok) return;
    const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `${row.document_number}.pdf`; a.click(); URL.revokeObjectURL(url);
  }
  const money = (minor: number) => `M ${(minor / 100).toFixed(2)}`;

  return <ControlShell title="Finance documents" subtitle="Quotations, pro-forma invoices and conversion to billing" userEmail={email}>
    {!owner ? <section className="surface-card p-6">Finance is restricted to the platform owner.</section> : <div className="space-y-4">
      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-5"><div><p className="eyebrow-label">Commercial documents</p><h1 className="mt-1 text-2xl font-black">Quotation / Pro-forma</h1><p className="mt-1 text-xs text-[var(--admin-muted)]">Create a multi-item commercial document, email its PDF and convert it to an invoice without retyping the work.</p></div><div className="rounded-2xl bg-[#eef6f2] px-5 py-3 text-right"><p className="text-[9px] font-black uppercase">Document total</p><p className="text-2xl font-black text-[#075135]">M {total.toFixed(2)}</p></div></div>
        <div className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-3"><label className="text-xs font-bold">Document type<select className="input mt-1" value={type} onChange={(e) => setType(e.target.value as "quotation" | "proforma")}><option value="quotation">Quotation</option><option value="proforma">Pro-forma invoice</option></select></label><label className="text-xs font-bold">Saved client<select className="input mt-1" value={clientId} onChange={(e) => chooseClient(e.target.value)}><option value="">Manual client</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label className="text-xs font-bold">Payment terms (days)<input className="input mt-1" type="number" min="0" max="365" value={terms} onChange={(e) => setTerms(e.target.value)} /></label></div>
          <div className="grid gap-3 md:grid-cols-2"><label className="text-xs font-bold">Client / company<input className="input mt-1" value={clientName} onChange={(e) => setClientName(e.target.value)} /></label><label className="text-xs font-bold">Receiving email<input className="input mt-1" type="email" value={recipientEmail} onChange={(e) => setRecipientEmail(e.target.value)} /></label></div>
          <div className="grid gap-3 md:grid-cols-2"><label className="text-xs font-bold">Address<input className="input mt-1" value={address} onChange={(e) => setAddress(e.target.value)} /></label><label className="text-xs font-bold">{type === "quotation" ? "Valid until" : "Optional validity date"}<input className="input mt-1" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></label></div>
          <div className="rounded-2xl border p-4"><div className="mb-3 flex items-center justify-between"><div><p className="font-black">Line items</p><p className="text-[10px] text-[var(--admin-muted)]">Up to eight services/items per document.</p></div><button className="btn-secondary" disabled={lines.length >= 8} onClick={addLine}><Plus size={14} />Add item</button></div><div className="space-y-3">{lines.map((line, i) => <div key={i} className="grid gap-2 rounded-xl bg-[#fafcfb] p-3 lg:grid-cols-[2fr_2fr_.6fr_.8fr_.8fr_auto]"><input className="input" placeholder="Description" value={line.description} onChange={(e) => updateLine(i, "description", e.target.value)} /><input className="input" placeholder="Details" value={line.details} onChange={(e) => updateLine(i, "details", e.target.value)} /><input className="input" type="number" min="1" value={line.quantity} onChange={(e) => updateLine(i, "quantity", e.target.value)} /><input className="input" type="number" min="0" step="0.01" value={line.rate} onChange={(e) => updateLine(i, "rate", e.target.value)} /><input className="input" type="number" min="0" step="0.01" value={line.tax} onChange={(e) => updateLine(i, "tax", e.target.value)} /><button className="btn-secondary" disabled={lines.length === 1} onClick={() => removeLine(i)}><Trash2 size={14} /></button></div>)}</div></div>
          <label className="text-xs font-bold">Notes<textarea className="input mt-1 min-h-24" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Commercial terms or notes for the client" /></label>
          <button className="btn-primary" disabled={busy} onClick={() => void create()}><FilePlus2 size={15} />Create {type === "quotation" ? "quotation" : "pro-forma"}</button>
        </div>
      </section>
      {message ? <div className="surface-card p-3 text-xs font-bold">{message}</div> : null}
      <section className="surface-card overflow-hidden"><div className="flex items-center justify-between border-b p-4"><div><p className="eyebrow-label">Document register</p><h2 className="mt-1 font-black">Quotations & pro-formas</h2></div><span className="rounded-xl bg-[#eef6f2] px-3 py-2 text-xs font-black">{documents.length} documents</span></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Document</th><th className="p-3">Client</th><th className="p-3">Type</th><th className="p-3">Total</th><th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead><tbody>{documents.map((row) => <tr key={row.id} className="border-t align-top"><td className="p-3 font-mono font-bold">{row.document_number}</td><td className="p-3"><p className="font-bold">{row.client_name}</p><p className="text-[10px] text-[var(--admin-muted)]">{row.recipient_email}</p></td><td className="p-3 capitalize">{row.document_type === "proforma" ? "Pro-forma" : "Quotation"}</td><td className="p-3 font-black">{money(row.total_minor)}</td><td className="p-3"><span className="rounded-full bg-[#eef3f7] px-2 py-1 text-[9px] font-black uppercase">{row.status}</span></td><td className="p-3"><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => void pdf(row)}><Download size={13} />PDF</button>{row.status !== "converted" ? <><button className="btn-secondary" disabled={busy} onClick={() => void action(row, "send")}><Send size={13} />Send</button><button className="btn-secondary" disabled={busy} onClick={() => void action(row, "status", { status: "accepted" })}><CheckCircle2 size={13} />Accept</button><button className="btn-secondary" disabled={busy} onClick={() => void action(row, "status", { status: "rejected" })}><XCircle size={13} />Reject</button><button className="btn-primary" disabled={busy} onClick={() => { if (window.confirm(`Convert ${row.document_number} to an invoice?`)) void action(row, "convert"); }}><FileCheck2 size={13} />Convert</button><button className="btn-secondary" disabled={busy} onClick={() => void remove(row)}><Trash2 size={13} />Delete</button></> : <span className="flex items-center gap-1 text-[10px] font-bold text-[#146b3a]"><ReceiptText size={13} />Invoice created</span>}</div></td></tr>)}{!documents.length ? <tr><td colSpan={6} className="p-8 text-center text-[var(--admin-muted)]">No quotations or pro-forma invoices yet.</td></tr> : null}</tbody></table></div></section>
    </div>}
  </ControlShell>;
}
