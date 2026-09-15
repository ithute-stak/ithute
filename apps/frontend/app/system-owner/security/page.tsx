"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { KeyRound, LockKeyhole, RefreshCw, ShieldAlert, ShieldCheck, Smartphone, UserRoundCheck, UsersRound } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type AdminStatus = {
  platform_owner: boolean;
  linked: boolean;
  elevated: boolean;
  bootstrap_link_available?: boolean;
};

type Overview = {
  auth?: {
    users?: { total?: number; active?: number; platform_admins?: number; mfa_enabled?: number; locked?: number };
    sessions?: { active?: number; revoked?: number };
    applications?: { total?: number; active?: number };
    security?: { audit_events?: number; pending_push_events?: number };
  };
  push?: Record<string, unknown>;
};

type UserRow = {
  id: string;
  email?: string | null;
  phone?: string | null;
  display_name: string;
  is_active: boolean;
  is_platform_admin: boolean;
  mfa_enabled: boolean;
  email_verified: boolean;
  phone_verified: boolean;
  failed_login_attempts: number;
  locked_until?: string | null;
  last_login_at?: string | null;
  created_at?: string | null;
};

function Metric({ label, value, icon: Icon, note }: { label: string; value: number | string; icon: typeof ShieldCheck; note: string }) {
  return <article className="surface-card p-4"><div className="flex items-center justify-between"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{label}</p><Icon size={15} /></div><p className="mt-3 text-3xl font-black">{value}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{note}</p></article>;
}

export default function OwnerSecurityPage() {
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const admin = await apiJson<AdminStatus>("/platform/ithute/admin/status", { ttlMs: 0, force: true });
      setStatus(admin);
      if (!admin.elevated) { setOverview(null); setUsers([]); return; }
      const [summary, rows] = await Promise.all([
        apiJson<Overview>("/platform/ithute/overview", { ttlMs: 0, force: true }),
        apiJson<UserRow[]>(`/platform/ithute/auth/users?limit=200${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`, { ttlMs: 0, force: true }),
      ]);
      setOverview(summary);
      setUsers(rows);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load Security Centre.");
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => { void load(); }, [load]);

  const auth = overview?.auth;
  const risky = useMemo(() => users.filter((user) => !user.is_active || user.failed_login_attempts > 0 || Boolean(user.locked_until) || !user.mfa_enabled), [users]);

  async function revoke(user: UserRow) {
    if (!window.confirm(`Revoke active central Ithute sessions for ${user.display_name}?`)) return;
    setBusy(user.id);
    setError("");
    setMessage("");
    try {
      const result = await apiMutation<{ revoked?: number }>(`/platform/ithute/auth/users/${user.id}/revoke-sessions`, { method: "POST", credentials: "include" }, ["/platform/ithute"]);
      setMessage(`Sessions revoked for ${user.display_name}: ${result?.revoked ?? 0}.`);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to revoke sessions.");
    } finally { setBusy(""); }
  }

  async function unlock(user: UserRow) {
    setBusy(user.id);
    setError("");
    setMessage("");
    try {
      await apiMutation(`/platform/ithute/auth/users/${user.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unlock: true }),
      }, ["/platform/ithute"]);
      setMessage(`${user.display_name} has been unlocked.`);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to unlock account.");
    } finally { setBusy(""); }
  }

  return (
    <ControlShell title="Security Centre" subtitle="Central Ithute identity, MFA, sessions and account-security operations">
      <div className="space-y-5 pb-20">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">Owner-only security</p><h1 className="mt-2 text-3xl font-black">Security Centre</h1><p className="mt-2 max-w-2xl text-[11px] leading-5 text-[#c8d8d2]">Central identity remains the authority for MFA, account locks and session revocation. Sensitive actions require a fresh Ithute Auth admin step-up.</p></div><button onClick={() => void load()} disabled={loading} className="rounded-xl bg-[#d8c56a] px-4 py-2.5 text-[10px] font-black text-[#123a38]"><RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`} />Refresh</button></div>
          </div>
          {error ? <div className="border-t border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
          {message ? <div className="border-t border-emerald-200 bg-emerald-50 p-3 text-[10px] font-bold text-emerald-700">{message}</div> : null}
        </section>

        {status && !status.elevated ? <section className="surface-card p-6"><div className="flex gap-3"><LockKeyhole className="mt-0.5 text-amber-600" size={20} /><div><h2 className="text-lg font-black">Central admin step-up required</h2><p className="mt-2 max-w-2xl text-[10px] leading-5 text-[var(--admin-muted)]">Your normal Control Centre session is deliberately not enough for global identity administration. Re-authenticate with the configured Ithute System Owner account to unlock Security Centre controls.</p><a href="/api/v1/platform/ithute/admin/login" className="btn-primary mt-4 inline-flex"><KeyRound size={14} />Authenticate with Ithute Auth</a></div></div></section> : null}

        {status?.elevated && auth ? <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Active identities" value={auth.users?.active ?? 0} icon={UsersRound} note={`${auth.users?.total ?? 0} total central accounts`} />
            <Metric label="MFA enabled" value={auth.users?.mfa_enabled ?? 0} icon={Smartphone} note="TOTP-protected accounts" />
            <Metric label="Active sessions" value={auth.sessions?.active ?? 0} icon={UserRoundCheck} note={`${auth.sessions?.revoked ?? 0} revoked historically`} />
            <Metric label="Locked accounts" value={auth.users?.locked ?? 0} icon={ShieldAlert} note={`${auth.security?.pending_push_events ?? 0} pending auth push events`} />
          </section>

          <section className="surface-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Identity posture</p><h2 className="mt-1 text-lg font-black">Accounts requiring attention</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Accounts appear here when MFA is off, login failures exist, the account is locked or it is disabled.</p></div><div className="flex gap-2"><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search user" className="rounded-xl border border-[var(--admin-line)] px-3 py-2 text-[10px]" /><button onClick={() => void load()} className="btn-secondary">Search</button></div></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[900px] text-left text-[10px]"><thead><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]"><th className="p-3">Account</th><th className="p-3">MFA</th><th className="p-3">Failures</th><th className="p-3">Lock</th><th className="p-3">Last login</th><th className="p-3">State</th><th className="p-3">Action</th></tr></thead><tbody>{risky.map((user) => <tr key={user.id} className="border-b border-[var(--admin-line)] last:border-0"><td className="p-3"><p className="font-black">{user.display_name}</p><p className="text-[8px] text-[var(--admin-muted)]">{user.email || user.phone || user.id}</p></td><td className="p-3">{user.mfa_enabled ? "Enabled" : "Off"}</td><td className="p-3">{user.failed_login_attempts}</td><td className="p-3">{user.locked_until ? new Date(user.locked_until).toLocaleString() : "—"}</td><td className="p-3">{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}</td><td className="p-3">{user.is_active ? "Active" : "Disabled"}</td><td className="p-3"><div className="flex gap-1">{user.locked_until || user.failed_login_attempts ? <button disabled={busy === user.id} onClick={() => void unlock(user)} className="rounded-lg border px-2 py-1 font-black">Unlock</button> : null}<button disabled={busy === user.id} onClick={() => void revoke(user)} className="rounded-lg border border-red-200 bg-red-50 px-2 py-1 font-black text-red-700">Revoke sessions</button></div></td></tr>)}</tbody></table>{!risky.length ? <div className="py-8 text-center text-[10px] text-emerald-700"><ShieldCheck size={18} className="mx-auto mb-2" />No matching account-security warnings.</div> : null}</div>
          </section>
        </> : null}
      </div>
    </ControlShell>
  );
}
