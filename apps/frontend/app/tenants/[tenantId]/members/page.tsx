"use client";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
const ROLES = ["tenant_admin", "dns_admin", "mail_admin", "auditor", "member"];

type Member = { id: string; user_id: string; email: string; full_name: string; role: string; status: string };
type Invite = { id: string; email: string; role: string; expires_at: string; accepted_at?: string };

export default function TeamPage() {
  const params = useParams<{ tenantId: string }>();
  const router = useRouter();
  const tenantId = params.tenantId;
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [message, setMessage] = useState("");
  const [inviteToken, setInviteToken] = useState("");

  async function request(path: string, init?: RequestInit) {
    const r = await fetch(`${API}${path}`, { credentials: "include", ...init });
    if (r.status === 401) { router.replace("/login"); throw new Error("unauthorized"); }
    return r;
  }

  async function load() {
    const [m, i] = await Promise.all([
      request(`/tenants/${tenantId}/members`),
      request(`/tenants/${tenantId}/invitations`),
    ]);
    if (m.ok) setMembers(await m.json());
    if (i.ok) setInvites(await i.json());
  }

  useEffect(() => { load().catch(() => undefined); }, [tenantId]);

  async function invite(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setMessage(""); setInviteToken("");
    const form = new FormData(e.currentTarget);
    const r = await request(`/tenants/${tenantId}/invitations`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), role: form.get("role") }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) { setMessage(body.detail || "Invitation failed"); return; }
    setInviteToken(body.token || "");
    setMessage("Invitation created. The token is shown once until email delivery is connected.");
    e.currentTarget.reset();
    await load();
  }

  async function updateMember(id: string, patch: Record<string, string>) {
    const r = await request(`/tenants/${tenantId}/members/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
    });
    const body = await r.json().catch(() => ({}));
    setMessage(r.ok ? "Membership updated." : body.detail || "Update failed");
    if (r.ok) await load();
  }

  async function cancelInvite(id: string) {
    const r = await request(`/tenants/${tenantId}/invitations/${id}`, { method: "DELETE" });
    setMessage(r.ok ? "Invitation cancelled." : "Unable to cancel invitation.");
    if (r.ok) await load();
  }

  return (
    <main className="page"><section className="card">
      <div className="brand">Company identity</div><h1>Team & access</h1>
      <p className="muted">Manage company members, granular roles and pending invitations.</p>
      <form onSubmit={invite} className="tile" style={{ marginBottom: 20 }}>
        <h2>Invite employee</h2><label>Email</label><input name="email" type="email" required />
        <label>Role</label><select name="role" defaultValue="member">{ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}</select>
        <button className="btn" type="submit">Create invitation</button>
      </form>
      {message && <p>{message}</p>}{inviteToken && <p style={{ wordBreak: "break-all" }}><b>One-time invitation token:</b> {inviteToken}</p>}
      <h2>Members</h2><div className="grid">{members.map((m) => <div className="tile" key={m.id}>
        <b>{m.full_name}</b><p className="muted">{m.email}</p><p>Status: {m.status}</p>
        <select value={m.role} onChange={(e) => updateMember(m.id, { role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}</select>
        {m.status === "active" ? <button className="btn" onClick={() => updateMember(m.id, { status: "suspended" })}>Suspend</button> : <button className="btn" onClick={() => updateMember(m.id, { status: "active" })}>Reactivate</button>}
      </div>)}</div>
      <h2 style={{ marginTop: 28 }}>Invitations</h2><div className="grid">{invites.map((i) => <div className="tile" key={i.id}><b>{i.email}</b><p>Role: {i.role.replaceAll("_", " ")}</p><p className="muted">Expires {new Date(i.expires_at).toLocaleString()}</p><p>{i.accepted_at ? "Accepted" : "Pending"}</p>{!i.accepted_at && <button className="btn" onClick={() => cancelInvite(i.id)}>Cancel</button>}</div>)}</div>
    </section></main>
  );
}
