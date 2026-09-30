"use client";

import { useEffect, useState } from "react";
import { Bell, BellOff, Plus, Save, Search, Trash2, Users } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { financeRoleRank, useFinanceAccess } from "../_components/use-finance-access";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Client = {
  id: string; name: string; email: string; address: string; phone: string;
  default_service: string; default_details: string; default_quantity: number;
  default_rate_minor: number; default_tax_minor: number; payment_terms_days: number;
  active: boolean; notes: string;
};

type Form = {
  name: string; email: string; address: string; phone: string; service: string;
  details: string; quantity: string; rate: string; tax: string; terms: string; notes: string; active: boolean;
};

const empty: Form = { name: "", email: "", address: "Maseru, Lesotho", phone: "", service: "iMail Professional Business Email Service", details: "Monthly managed iMail service and business mailbox access", quantity: "1", rate: "185.00", tax: "0.00", terms: "7", notes: "", active: true };

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
}

export default function FinanceClientsPage() {
  const { email, allowed, role, loading: accessLoading } = useFinanceAccess();
  const [items, setItems] = useState<Client[]>([]);
  const [reminders, setReminders] = useState<Record<string, boolean>>({});
  const [form, setForm] = useState<Form>(empty);
  const [editing, setEditing] = useState("");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const canWrite = financeRoleRank(role) >= 2;
  const canAdmin = financeRoleRank(role) >= 4;

  useEffect(() => { if (allowed) void load(); }, [allowed]);

  async function load(q = query) {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    const [r, p] = await Promise.all([api(`/finance/clients${suffix}`), api("/finance/preferences/clients")]);
    if (r.ok) setItems((await r.json()).items || []);
    if (p.ok) {
      const body = await p.json(); const map: Record<string, boolean> = {};
      for (const row of body.items || []) map[row.client_id] = Boolean(row.reminders_enabled);
      setReminders(map);
    }
  }

  function edit(client: Client) {
    if (!canWrite) return;
    setEditing(client.id);
    setForm({ name: client.name, email: client.email, address: client.address, phone: client.phone, service: client.default_service, details: client.default_details, quantity: String(client.default_quantity), rate: (client.default_rate_minor / 100).toFixed(2), tax: (client.default_tax_minor / 100).toFixed(2), terms: String(client.payment_terms_days), notes: client.notes || "", active: client.active });
  }

  async function save() {
    if (!canWrite) return setMessage("Your Finance role is read-only.");
    if (!form.name.trim() || !form.email.trim()) { setMessage("Client name and email are required."); return; }
    setBusy(true); setMessage("");
    const payload = { name: form.name.trim(), email: form.email.trim(), address: form.address.trim(), phone: form.phone.trim(), default_service: form.service.trim(), default_details: form.details.trim(), default_quantity: Math.max(1, Number(form.quantity) || 1), default_rate_minor: Math.max(0, Math.round((Number(form.rate) || 0) * 100)), default_tax_minor: Math.max(0, Math.round((Number(form.tax) || 0) * 100)), payment_terms_days: Math.max(0, Number(form.terms) || 0), active: form.active, notes: form.notes.trim() };
    try {
      const r = await api(editing ? `/finance/clients/${editing}` : "/finance/clients", { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to save client"));
      setMessage(`${form.name.trim()} ${editing ? "updated" : "saved"}.`); setForm(empty); setEditing(""); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to save client"); } finally { setBusy(false); }
  }

  async function toggleReminders(client: Client) {
    if (!canWrite) return setMessage("Your Finance role is read-only.");
    const enabled = !(reminders[client.id] ?? true); setBusy(true);
    try {
      const r = await api(`/finance/preferences/clients/${client.id}/reminders`, { method: "PATCH", body: JSON.stringify({ enabled }) });
      const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(data.detail || "Unable to update reminder preference"));
      setReminders((prev) => ({ ...prev, [client.id]: enabled }));
      setMessage(`${client.name}: automatic reminders ${enabled ? "enabled" : "paused"}.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to update reminders"); } finally { setBusy(false); }
  }

  async function remove(client: Client) {
    if (!canAdmin) return setMessage("Finance Admin access is required to delete clients.");
    if (!window.confirm(`Delete finance client ${client.name}? Existing invoices will remain.`)) return;
    setBusy(true); try { const r = await api(`/finance/clients/${client.id}`, { method: "DELETE" }); if (!r.ok) throw new Error("Unable to delete client"); await load(); setMessage(`${client.name} deleted.`); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to delete client"); } finally { setBusy(false); }
  }

  return <ControlShell title="Finance clients" subtitle="Reusable customer accounts, billing defaults and reminder controls" userEmail={email}>
    {accessLoading ? <section className="surface-card p-6">Checking Finance access…</section> : !allowed ? <section className="surface-card p-6">Finance access is required.</section> : <div className={`grid gap-4 ${canWrite ? "xl:grid-cols-[420px_1fr]" : ""}`}>
      {canWrite ? <section className="surface-card p-5">
        <div className="flex items-center gap-2"><Users size={18} /><h1 className="font-black">{editing ? "Edit client" : "New client"}</h1></div>
        <div className="mt-4 space-y-3">
          <label className="text-xs font-bold">Client / company name<input className="input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="text-xs font-bold">Billing email<input className="input mt-1" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label className="text-xs font-bold">Address<input className="input mt-1" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></label>
          <label className="text-xs font-bold">Phone<input className="input mt-1" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <label className="text-xs font-bold">Default service<input className="input mt-1" value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} /></label>
          <label className="text-xs font-bold">Default details<textarea className="input mt-1 min-h-20" value={form.details} onChange={(e) => setForm({ ...form, details: e.target.value })} /></label>
          <div className="grid grid-cols-2 gap-2"><label className="text-xs font-bold">Qty<input className="input mt-1" type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label><label className="text-xs font-bold">Rate (M)<input className="input mt-1" type="number" min="0" step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} /></label><label className="text-xs font-bold">Tax (M)<input className="input mt-1" type="number" min="0" step="0.01" value={form.tax} onChange={(e) => setForm({ ...form, tax: e.target.value })} /></label><label className="text-xs font-bold">Payment terms<input className="input mt-1" type="number" min="0" max="365" value={form.terms} onChange={(e) => setForm({ ...form, terms: e.target.value })} /></label></div>
          <label className="text-xs font-bold">Notes<textarea className="input mt-1 min-h-20" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
          <label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />Active client</label>
          <div className="flex gap-2"><button className="btn-primary" disabled={busy} onClick={() => void save()}><Save size={14} />{editing ? "Update" : "Save client"}</button>{editing ? <button className="btn-secondary" onClick={() => { setEditing(""); setForm(empty); }}><Plus size={14} />New</button> : null}</div>
          {message ? <p className="text-xs font-bold">{message}</p> : null}
        </div>
      </section> : null}
      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><p className="eyebrow-label">Client accounts</p><h2 className="mt-1 font-black">Finance clients</h2>{!canWrite ? <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Read-only Finance access</p> : null}</div><div className="flex min-w-64 items-center gap-2 rounded-xl border px-3"><Search size={14} /><input className="w-full bg-transparent py-2 text-xs outline-none" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void load(e.currentTarget.value); }} placeholder="Search name, email or phone" /></div></div>
        <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Client</th><th className="p-3">Email / phone</th><th className="p-3">Default service</th><th className="p-3">Monthly default</th><th className="p-3">Terms</th><th className="p-3">Reminders</th><th className="p-3">Status</th><th className="p-3">Actions</th></tr></thead><tbody>{items.map((c) => { const reminderOn = reminders[c.id] ?? true; return <tr key={c.id} className="border-t"><td className="p-3 font-bold">{c.name}<p className="mt-1 text-[9px] font-normal text-[var(--admin-muted)]">{c.address}</p></td><td className="p-3">{c.email}<p className="mt-1 text-[9px] text-[var(--admin-muted)]">{c.phone || "—"}</p></td><td className="p-3">{c.default_service || "—"}</td><td className="p-3 font-black">M {(c.default_quantity * c.default_rate_minor / 100 + c.default_tax_minor / 100).toFixed(2)}</td><td className="p-3">{c.payment_terms_days} days</td><td className="p-3">{canWrite ? <button className="btn-secondary" disabled={busy} onClick={() => void toggleReminders(c)}>{reminderOn ? <Bell size={13} /> : <BellOff size={13} />}{reminderOn ? "On" : "Paused"}</button> : <span>{reminderOn ? "On" : "Paused"}</span>}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${c.active ? "bg-[#e9f7ee] text-[#146b3a]" : "bg-[#eef3f7] text-[#526474]"}`}>{c.active ? "active" : "inactive"}</span></td><td className="p-3"><div className="flex gap-2">{canWrite ? <button className="btn-secondary" onClick={() => edit(c)}>Edit</button> : null}{canAdmin ? <button className="btn-secondary" disabled={busy} onClick={() => void remove(c)}><Trash2 size={13} />Delete</button> : null}</div></td></tr>})}{!items.length ? <tr><td colSpan={8} className="p-8 text-center text-[var(--admin-muted)]">No finance clients yet.</td></tr> : null}</tbody></table></div>
      </section>
    </div>}
  </ControlShell>;
}
