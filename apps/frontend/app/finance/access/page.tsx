"use client";

import { useEffect, useState } from "react";
import { Copy, KeyRound, Link2, ShieldCheck, Trash2 } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
async function api(path: string, init?: RequestInit) { return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } }); }

type User = { id: string; email: string; full_name: string; is_platform_owner: boolean };
type Grant = { id: string; user_id: string; email?: string | null; full_name?: string | null; role: string; active: boolean };
type Client = { id: string; name: string; email: string };

export default function FinanceAccessPage() {
  const [email, setEmail] = useState(""); const [owner, setOwner] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const [users, setUsers] = useState<User[]>([]); const [grants, setGrants] = useState<Grant[]>([]); const [clients, setClients] = useState<Client[]>([]);
  const [userId, setUserId] = useState(""); const [role, setRole] = useState("viewer"); const [clientId, setClientId] = useState(""); const [hours, setHours] = useState("72"); const [portalUrl, setPortalUrl] = useState("");

  async function load() {
    const [u, g, c] = await Promise.all([api("/finance/completion/eligible-users"), api("/finance/completion/roles"), api("/finance/clients?active=true")]);
    if (u.ok) setUsers((await u.json()).items || []); if (g.ok) setGrants((await g.json()).items || []); if (c.ok) setClients((await c.json()).items || []);
  }
  useEffect(() => { void (async () => { const me = await api("/auth/me"); if (!me.ok) return; const body = await me.json(); setEmail(body.email || ""); setOwner(Boolean(body.is_platform_owner)); if (body.is_platform_owner) await load(); })(); }, []);

  async function saveRole() {
    if (!userId) return setMessage("Select a user first."); setBusy(true); setMessage("");
    try { const r = await api("/finance/completion/roles", { method: "PUT", body: JSON.stringify({ user_id: userId, role, active: true }) }); const body = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(body.detail || "Unable to save role")); setMessage(`Finance ${role} access granted.`); await load(); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to save role"); } finally { setBusy(false); }
  }
  async function removeRole(id: string) { if (!window.confirm("Remove this user's Finance access?")) return; setBusy(true); const r = await api(`/finance/completion/roles/${id}`, { method: "DELETE" }); setBusy(false); if (r.ok) { setMessage("Finance access removed."); await load(); } else setMessage("Unable to remove Finance access."); }
  async function makePortal(sendEmail: boolean) {
    if (!clientId) return setMessage("Select a client first."); setBusy(true); setPortalUrl(""); setMessage("");
    try { const r = await api(`/finance/completion/portal-links/${clientId}`, { method: "POST", body: JSON.stringify({ expires_hours: Number(hours) || 72, send_email: sendEmail }) }); const body = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(body.detail || "Unable to create portal link")); setPortalUrl(body.portal_url || ""); setMessage(sendEmail ? `Secure portal link emailed to ${body.recipient}.` : "Secure portal link created."); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to create portal link"); } finally { setBusy(false); }
  }

  return <ControlShell title="Finance access" subtitle="Delegated roles and secure client self-service portal" userEmail={email}>
    {!owner ? <section className="surface-card p-6">Only the platform owner can manage Finance access.</section> : <div className="space-y-4 pb-24">
      {message ? <div className="surface-card px-4 py-3 text-xs font-bold">{message}</div> : null}
      <section className="surface-card p-5"><div className="flex items-center gap-2"><ShieldCheck size={18} /><h1 className="text-lg font-black">Delegated Finance roles</h1></div><p className="mt-1 text-xs text-[var(--admin-muted)]">Viewer = read-only, Clerk = daily operations, Approver = sensitive financial decisions, Admin = full Finance administration. Platform owner always retains full access.</p><div className="mt-4 grid gap-2 md:grid-cols-[1fr_180px_auto]"><select className="input" value={userId} onChange={(e) => setUserId(e.target.value)}><option value="">Select active Ithute user</option>{users.filter((u) => !u.is_platform_owner).map((u) => <option key={u.id} value={u.id}>{u.email}{u.full_name ? ` · ${u.full_name}` : ""}</option>)}</select><select className="input" value={role} onChange={(e) => setRole(e.target.value)}><option value="viewer">Viewer</option><option value="clerk">Clerk</option><option value="approver">Approver</option><option value="admin">Admin</option></select><button disabled={busy} onClick={() => void saveRole()} className="btn-primary">Grant / update</button></div><div className="mt-4 overflow-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-3">User</th><th className="p-3">Role</th><th className="p-3">Status</th><th className="p-3 text-right">Action</th></tr></thead><tbody>{grants.map((g) => <tr key={g.id} className="border-t"><td className="p-3"><p className="font-black">{g.email || g.user_id}</p><p className="text-[10px] text-[var(--admin-muted)]">{g.full_name || ""}</p></td><td className="p-3 uppercase font-black">{g.role}</td><td className="p-3">{g.active ? "Active" : "Paused"}</td><td className="p-3 text-right"><button disabled={busy} onClick={() => void removeRole(g.id)} className="btn-secondary inline-flex items-center gap-1"><Trash2 size={13} />Remove</button></td></tr>)}</tbody></table></div></section>
      <section className="surface-card p-5"><div className="flex items-center gap-2"><KeyRound size={18} /><h2 className="font-black">Secure client portal</h2></div><p className="mt-1 text-xs text-[var(--admin-muted)]">Create a time-limited link. The token stays in the browser URL fragment and is not sent in normal HTTP URL logs.</p><div className="mt-4 grid gap-2 md:grid-cols-[1fr_150px_auto_auto]"><select className="input" value={clientId} onChange={(e) => setClientId(e.target.value)}><option value="">Select client</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.email}</option>)}</select><input className="input" type="number" min="1" max="720" value={hours} onChange={(e) => setHours(e.target.value)} /><button disabled={busy} onClick={() => void makePortal(false)} className="btn-secondary inline-flex items-center gap-2"><Link2 size={14} />Create link</button><button disabled={busy} onClick={() => void makePortal(true)} className="btn-primary">Create & email</button></div>{portalUrl ? <div className="mt-3 rounded-xl border bg-[#f6faf8] p-3"><p className="break-all text-xs font-bold">{portalUrl}</p><button onClick={() => void navigator.clipboard.writeText(portalUrl)} className="mt-2 text-xs font-black underline"><Copy size={13} className="mr-1 inline" />Copy link</button></div> : null}</section>
    </div>}
  </ControlShell>;
}
