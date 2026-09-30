"use client";

import { useEffect, useMemo, useState } from "react";
import { Banknote, FileUp, Landmark, Link2, PlusCircle, RefreshCw, WalletCards } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const money = (minor = 0) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
async function api(path: string, init?: RequestInit) { return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } }); }

type Client = { id: string; name: string; email: string };
type Expense = { id: string; expense_date: string; vendor: string; category: string; description: string; amount_minor: number; tax_minor: number; payment_method: string; reference: string; recurring: boolean; status: string };
type InvoiceMini = { id: string; invoice_number: string; client_name: string; outstanding_minor: number };
type BankRow = { id: string; transaction_date: string; amount_minor: number; description: string; reference: string; status: string; suggestion?: { reason: string; invoice: InvoiceMini } | null };
type ServiceLink = { id: string; client_id: string; source_type: string; source_ref: string; service_label: string; quantity: number; rate_minor: number; tax_minor: number; send_day: number; due_days: number; enabled: boolean; schedule_id?: string | null };
type Pnl = { start: string; end: string; revenue_minor: number; expense_minor: number; net_profit_minor: number; expense_by_category: Record<string, number>; basis: string };

function isoToday() { return new Date().toISOString().slice(0, 10); }
function monthStart() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`; }
function monthEnd() { const d = new Date(); return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10); }

function parseCsvLine(line: string) {
  const out: string[] = []; let value = ""; let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { if (quoted && line[i + 1] === '"') { value += '"'; i++; } else quoted = !quoted; }
    else if (ch === "," && !quoted) { out.push(value.trim()); value = ""; }
    else value += ch;
  }
  out.push(value.trim()); return out;
}
function normalizeDate(value: string) {
  const clean = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) return clean;
  const match = clean.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
  if (!match) return "";
  return `${match[3]}-${match[2].padStart(2, "0")}-${match[1].padStart(2, "0")}`;
}
function parseAmount(value: string) {
  const n = Number(value.replace(/[^0-9.-]/g, "")); return Number.isFinite(n) ? Math.round(n * 100) : NaN;
}

export default function FinanceAccountingPage() {
  const [email, setEmail] = useState(""); const [owner, setOwner] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const [expenses, setExpenses] = useState<Expense[]>([]); const [bankRows, setBankRows] = useState<BankRow[]>([]); const [clients, setClients] = useState<Client[]>([]); const [links, setLinks] = useState<ServiceLink[]>([]);
  const [start, setStart] = useState(monthStart()); const [end, setEnd] = useState(monthEnd()); const [pnl, setPnl] = useState<Pnl | null>(null);
  const [expense, setExpense] = useState({ expense_date: isoToday(), vendor: "", category: "Operations", description: "", amount: "", tax: "0", payment_method: "bank_transfer", reference: "", recurring: false });
  const [service, setService] = useState({ client_id: "", source_type: "service", source_ref: "", service_label: "", details: "", quantity: "1", rate: "", tax: "0", send_day: "1", due_days: "7" });

  async function load() {
    const [e, b, c, l, p] = await Promise.all([
      api("/finance/accounting/expenses?status=posted"), api("/finance/accounting/bank?status=unmatched"), api("/finance/clients?active=true"), api("/finance/accounting/service-links"), api(`/finance/accounting/pnl?start=${start}&end=${end}`),
    ]);
    if (e.ok) setExpenses((await e.json()).items || []); if (b.ok) setBankRows((await b.json()).items || []); if (c.ok) setClients((await c.json()).items || []); if (l.ok) setLinks((await l.json()).items || []); if (p.ok) setPnl(await p.json());
  }

  useEffect(() => { void (async () => { const me = await api("/auth/me"); if (!me.ok) return; const body = await me.json(); setEmail(body.email || ""); setOwner(Boolean(body.is_platform_owner)); if (body.is_platform_owner) await load(); })(); }, []);
  useEffect(() => { if (owner) void (async () => { const r = await api(`/finance/accounting/pnl?start=${start}&end=${end}`); if (r.ok) setPnl(await r.json()); })(); }, [start, end, owner]);

  const expenseTotal = useMemo(() => expenses.reduce((sum, row) => sum + row.amount_minor + row.tax_minor, 0), [expenses]);

  async function addExpense() {
    if (!expense.vendor.trim() || !expense.category.trim() || !expense.amount) return setMessage("Vendor, category and amount are required.");
    setBusy(true); setMessage("");
    try {
      const r = await api("/finance/accounting/expenses", { method: "POST", body: JSON.stringify({ ...expense, amount_minor: Math.round(Number(expense.amount) * 100), tax_minor: Math.round(Number(expense.tax || 0) * 100), vendor: expense.vendor.trim(), category: expense.category.trim(), description: expense.description.trim(), reference: expense.reference.trim(), amount: undefined, tax: undefined }) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to save expense"));
      setExpense({ expense_date: isoToday(), vendor: "", category: "Operations", description: "", amount: "", tax: "0", payment_method: "bank_transfer", reference: "", recurring: false }); setMessage("Expense recorded."); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to save expense"); } finally { setBusy(false); }
  }

  async function voidExpense(id: string) { if (!window.confirm("Void this expense? It will stay in the audit history.")) return; setBusy(true); try { const r = await api(`/finance/accounting/expenses/${id}/void`, { method: "PATCH" }); if (!r.ok) throw new Error("Unable to void expense"); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to void expense"); } finally { setBusy(false); } }

  async function importCsv(file: File) {
    setBusy(true); setMessage("");
    try {
      const text = await file.text(); const lines = text.split(/\r?\n/).filter((line) => line.trim()); if (lines.length < 2) throw new Error("CSV has no transaction rows.");
      const headers = parseCsvLine(lines[0]).map((x) => x.toLowerCase().replace(/\s+/g, "_"));
      const index = (...names: string[]) => names.map((name) => headers.indexOf(name)).find((i) => i >= 0) ?? -1;
      const di = index("date", "transaction_date", "value_date"); const ai = index("amount", "credit", "value", "transaction_amount"); const ri = index("reference", "ref", "payment_reference"); const xi = index("description", "details", "narrative", "memo");
      if (di < 0 || ai < 0) throw new Error("CSV needs Date and Amount columns. Reference/Description are optional.");
      const rows = lines.slice(1).map(parseCsvLine).map((cols) => ({ transaction_date: normalizeDate(cols[di] || ""), amount_minor: parseAmount(cols[ai] || ""), reference: ri >= 0 ? cols[ri] || "" : "", description: xi >= 0 ? cols[xi] || "" : "" })).filter((row) => row.transaction_date && Number.isFinite(row.amount_minor));
      if (!rows.length) throw new Error("No valid bank transactions found in the CSV.");
      const r = await api("/finance/accounting/bank/import", { method: "POST", body: JSON.stringify({ source_name: "LPB", import_batch: file.name.slice(0, 120), rows }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Bank import failed"));
      setMessage(`Bank import complete: ${data.imported} added, ${data.duplicates} duplicates skipped.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Bank import failed"); } finally { setBusy(false); }
  }

  async function reconcile(row: BankRow) {
    const invoice = row.suggestion?.invoice; if (!invoice) return;
    if (!window.confirm(`Reconcile ${money(row.amount_minor)} to ${invoice.invoice_number} — ${invoice.client_name}?`)) return;
    setBusy(true); try { const r = await api(`/finance/accounting/bank/${row.id}/reconcile`, { method: "POST", body: JSON.stringify({ invoice_id: invoice.id }) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to reconcile")); setMessage(`${invoice.invoice_number} reconciled.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to reconcile"); } finally { setBusy(false); }
  }

  async function ignoreBank(id: string) { if (!window.confirm("Ignore this bank transaction for invoice reconciliation?")) return; setBusy(true); try { const r = await api(`/finance/accounting/bank/${id}/ignore`, { method: "PATCH" }); if (!r.ok) throw new Error("Unable to ignore transaction"); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to ignore transaction"); } finally { setBusy(false); } }

  async function addServiceLink() {
    if (!service.client_id || !service.source_ref.trim() || !service.service_label.trim() || !service.rate) return setMessage("Client, service reference, label and rate are required.");
    setBusy(true); setMessage("");
    try {
      const payload = { client_id: service.client_id, source_type: service.source_type, source_ref: service.source_ref.trim(), service_label: service.service_label.trim(), details: service.details.trim(), quantity: Number(service.quantity) || 1, rate_minor: Math.round(Number(service.rate) * 100), tax_minor: Math.round(Number(service.tax || 0) * 100), send_day: Number(service.send_day) || 1, due_days: Number(service.due_days) || 7, enabled: true };
      const r = await api("/finance/accounting/service-links", { method: "POST", body: JSON.stringify(payload) }); const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to link service"));
      setService({ client_id: "", source_type: "service", source_ref: "", service_label: "", details: "", quantity: "1", rate: "", tax: "0", send_day: "1", due_days: "7" }); setMessage("Service linked to recurring billing."); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to link service"); } finally { setBusy(false); }
  }

  async function toggleLink(id: string) { setBusy(true); try { const r = await api(`/finance/accounting/service-links/${id}/toggle`, { method: "PATCH" }); if (!r.ok) throw new Error("Unable to update service billing"); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to update service billing"); } finally { setBusy(false); } }

  return <ControlShell title="Finance accounting" subtitle="Bank reconciliation, expenses, management P&L and service-linked billing" userEmail={email}>
    {!owner ? <section className="surface-card p-6">Finance is restricted.</section> : <div className="space-y-4 pb-20">
      {message ? <div className="surface-card px-4 py-3 text-xs font-bold">{message}</div> : null}
      <section className="surface-card p-4">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow-label">Management P&amp;L</p><h1 className="mt-1 text-lg font-black">Revenue, expenses and profit</h1><p className="text-[10px] text-[var(--admin-muted)]">Management accrual view based on net issued invoices less posted expenses.</p></div><div className="flex gap-2"><label className="text-[10px] font-bold">From<input className="input mt-1" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label><label className="text-[10px] font-bold">To<input className="input mt-1" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label></div></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Revenue</p><p className="mt-2 text-xl font-black">{money(pnl?.revenue_minor || 0)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Expenses</p><p className="mt-2 text-xl font-black">{money(pnl?.expense_minor || 0)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Net profit</p><p className="mt-2 text-xl font-black">{money(pnl?.net_profit_minor || 0)}</p></div></div>
        {pnl?.expense_by_category && Object.keys(pnl.expense_by_category).length ? <div className="mt-3 flex flex-wrap gap-2">{Object.entries(pnl.expense_by_category).map(([category, amount]) => <span key={category} className="rounded-full border px-3 py-1.5 text-[10px] font-bold">{category}: {money(amount)}</span>)}</div> : null}
      </section>

      <div className="grid gap-4 xl:grid-cols-[400px_1fr]">
        <section className="surface-card p-4"><div className="flex items-center gap-2"><PlusCircle size={17} /><h2 className="font-black">Record expense</h2></div><div className="mt-3 grid gap-2">
          <input className="input" type="date" value={expense.expense_date} onChange={(e) => setExpense({ ...expense, expense_date: e.target.value })} /><input className="input" placeholder="Vendor" value={expense.vendor} onChange={(e) => setExpense({ ...expense, vendor: e.target.value })} /><input className="input" placeholder="Category" value={expense.category} onChange={(e) => setExpense({ ...expense, category: e.target.value })} /><textarea className="input min-h-16" placeholder="Description" value={expense.description} onChange={(e) => setExpense({ ...expense, description: e.target.value })} /><div className="grid grid-cols-2 gap-2"><input className="input" type="number" min="0" step="0.01" placeholder="Amount (M)" value={expense.amount} onChange={(e) => setExpense({ ...expense, amount: e.target.value })} /><input className="input" type="number" min="0" step="0.01" placeholder="Tax (M)" value={expense.tax} onChange={(e) => setExpense({ ...expense, tax: e.target.value })} /></div><input className="input" placeholder="Payment reference" value={expense.reference} onChange={(e) => setExpense({ ...expense, reference: e.target.value })} /><label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={expense.recurring} onChange={(e) => setExpense({ ...expense, recurring: e.target.checked })} />Recurring expense</label><button className="btn-primary" disabled={busy} onClick={() => void addExpense()}><Banknote size={14} />Save expense</button>
        </div></section>
        <section className="surface-card overflow-hidden"><div className="flex items-center justify-between border-b p-4"><div><p className="eyebrow-label">Expense register</p><h2 className="font-black">Posted expenses</h2></div><span className="text-xs font-black">{money(expenseTotal)}</span></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Date</th><th className="p-3">Vendor</th><th className="p-3">Category</th><th className="p-3">Amount</th><th className="p-3">Reference</th><th className="p-3">Action</th></tr></thead><tbody>{expenses.map((x) => <tr key={x.id} className="border-t"><td className="p-3">{x.expense_date}</td><td className="p-3 font-bold">{x.vendor}<p className="text-[9px] font-normal text-[var(--admin-muted)]">{x.description}</p></td><td className="p-3">{x.category}</td><td className="p-3 font-black">{money(x.amount_minor + x.tax_minor)}</td><td className="p-3">{x.reference || "—"}</td><td className="p-3"><button className="btn-secondary" disabled={busy} onClick={() => void voidExpense(x.id)}>Void</button></td></tr>)}{!expenses.length ? <tr><td colSpan={6} className="p-8 text-center text-[var(--admin-muted)]">No posted expenses yet.</td></tr> : null}</tbody></table></div></section>
      </div>

      <section className="surface-card overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div className="flex items-center gap-2"><Landmark size={17} /><div><p className="eyebrow-label">Bank reconciliation</p><h2 className="font-black">LPB transaction matching</h2><p className="text-[10px] text-[var(--admin-muted)]">Import CSV, skip duplicates, suggest invoice matches and reconcile in one click.</p></div></div><label className="btn-secondary cursor-pointer"><FileUp size={14} />Import CSV<input className="hidden" type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) void importCsv(f); e.currentTarget.value = ""; }} /></label></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Date</th><th className="p-3">Amount</th><th className="p-3">Reference / description</th><th className="p-3">Suggested invoice</th><th className="p-3">Actions</th></tr></thead><tbody>{bankRows.map((row) => <tr key={row.id} className="border-t"><td className="p-3">{row.transaction_date}</td><td className="p-3 font-black">{money(row.amount_minor)}</td><td className="p-3">{row.reference || "—"}<p className="text-[9px] text-[var(--admin-muted)]">{row.description}</p></td><td className="p-3">{row.suggestion ? <><span className="font-black">{row.suggestion.invoice.invoice_number}</span><p className="text-[9px] text-[var(--admin-muted)]">{row.suggestion.invoice.client_name} · {money(row.suggestion.invoice.outstanding_minor)}</p><p className="text-[9px] uppercase text-[var(--admin-muted)]">{row.suggestion.reason.replaceAll("_", " ")}</p></> : <span className="text-[var(--admin-muted)]">No confident match</span>}</td><td className="p-3"><div className="flex gap-2">{row.suggestion ? <button className="btn-primary" disabled={busy} onClick={() => void reconcile(row)}><WalletCards size={13} />Reconcile</button> : null}<button className="btn-secondary" disabled={busy} onClick={() => void ignoreBank(row.id)}>Ignore</button></div></td></tr>)}{!bankRows.length ? <tr><td colSpan={5} className="p-8 text-center text-[var(--admin-muted)]">No unmatched bank transactions.</td></tr> : null}</tbody></table></div></section>

      <div className="grid gap-4 xl:grid-cols-[400px_1fr]">
        <section className="surface-card p-4"><div className="flex items-center gap-2"><Link2 size={17} /><h2 className="font-black">Link service to billing</h2></div><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Creates and maintains the recurring invoice schedule for a live service.</p><div className="mt-3 grid gap-2"><select className="input" value={service.client_id} onChange={(e) => setService({ ...service, client_id: e.target.value })}><option value="">Select client</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name} — {c.email}</option>)}</select><select className="input" value={service.source_type} onChange={(e) => setService({ ...service, source_type: e.target.value })}><option value="service">Ithute service</option><option value="ithute_product">Registered Ithute product</option><option value="domain">Domain</option><option value="hosting">Hosting</option><option value="imail">iMail mailbox/service</option></select><input className="input" placeholder="Service reference (e.g. imail-client-01)" value={service.source_ref} onChange={(e) => setService({ ...service, source_ref: e.target.value })} /><input className="input" placeholder="Invoice service label" value={service.service_label} onChange={(e) => setService({ ...service, service_label: e.target.value })} /><textarea className="input min-h-16" placeholder="Billing details" value={service.details} onChange={(e) => setService({ ...service, details: e.target.value })} /><div className="grid grid-cols-2 gap-2"><input className="input" type="number" min="1" placeholder="Qty" value={service.quantity} onChange={(e) => setService({ ...service, quantity: e.target.value })} /><input className="input" type="number" min="0" step="0.01" placeholder="Rate (M)" value={service.rate} onChange={(e) => setService({ ...service, rate: e.target.value })} /><input className="input" type="number" min="1" max="31" placeholder="Send day" value={service.send_day} onChange={(e) => setService({ ...service, send_day: e.target.value })} /><input className="input" type="number" min="0" max="365" placeholder="Due days" value={service.due_days} onChange={(e) => setService({ ...service, due_days: e.target.value })} /></div><button className="btn-primary" disabled={busy} onClick={() => void addServiceLink()}><Link2 size={14} />Link & automate</button></div></section>
        <section className="surface-card overflow-hidden"><div className="flex items-center justify-between border-b p-4"><div><p className="eyebrow-label">Service billing</p><h2 className="font-black">Linked recurring services</h2></div><button className="btn-secondary" onClick={() => void load()}><RefreshCw size={13} />Refresh</button></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Service</th><th className="p-3">Client</th><th className="p-3">Monthly</th><th className="p-3">Schedule</th><th className="p-3">Status</th><th className="p-3">Action</th></tr></thead><tbody>{links.map((row) => <tr key={row.id} className="border-t"><td className="p-3 font-bold">{row.service_label}<p className="text-[9px] font-normal text-[var(--admin-muted)]">{row.source_type}: {row.source_ref}</p></td><td className="p-3">{clients.find((c) => c.id === row.client_id)?.name || row.client_id.slice(0, 8)}</td><td className="p-3 font-black">{money(row.quantity * row.rate_minor + row.tax_minor)}</td><td className="p-3">Day {row.send_day}<p className="text-[9px] text-[var(--admin-muted)]">Due +{row.due_days} days</p></td><td className="p-3"><span className="rounded-full border px-2 py-1 text-[9px] font-black uppercase">{row.enabled ? "active" : "paused"}</span></td><td className="p-3"><button className="btn-secondary" disabled={busy} onClick={() => void toggleLink(row.id)}>{row.enabled ? "Pause" : "Enable"}</button></td></tr>)}{!links.length ? <tr><td colSpan={6} className="p-8 text-center text-[var(--admin-muted)]">No service-linked billing yet.</td></tr> : null}</tbody></table></div></section>
      </div>
    </div>}
  </ControlShell>;
}
