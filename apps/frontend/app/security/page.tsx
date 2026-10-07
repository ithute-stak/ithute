"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ExternalLink, KeyRound, Laptop, LockKeyhole, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { ConfirmDialog, EmptyState, PageHeader, StatusBadge, Toast } from "@/components/ui-kit";
import { apiFetch } from "@/lib/platform-api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Session = {
  id: string;
  created_at: string;
  expires_at: string;
  user_agent?: string;
  ip_address?: string;
  revoked: boolean;
};

type Me = {
  email: string;
  mfa_enabled: boolean;
};

type AuthCapabilities = {
  local_auth_enabled: boolean;
  central_auth_enabled: boolean;
  local_security_controls_enabled: boolean;
};

type CentralAuthStatus = {
  enabled: boolean;
  linked: boolean;
  enforced: boolean;
  enforced_at?: string | null;
};

export default function SecurityPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [localControls, setLocalControls] = useState(false);
  const [centralStatus, setCentralStatus] = useState<CentralAuthStatus | null>(null);
  const [secret, setSecret] = useState("");
  const [uri, setUri] = useState("");
  const [code, setCode] = useState("");
  const [toast, setToast] = useState("");
  const [revokeAll, setRevokeAll] = useState(false);
  const [confirm, setConfirm] = useState("");

  async function load() {
    const [meResponse, capabilityResponse, centralResponse] = await Promise.all([
      apiFetch("/auth/me", { cache: "no-store" }),
      fetch(`${API}/auth/capabilities`, { cache: "no-store" }),
      apiFetch("/auth/ithute/status", { cache: "no-store" }),
    ]);

    if (meResponse.status === 401) {
      router.replace("/login");
      return;
    }
    if (meResponse.ok) setMe(await meResponse.json());

    const capabilities: AuthCapabilities | null = capabilityResponse.ok
      ? await capabilityResponse.json()
      : null;
    const central: CentralAuthStatus | null = centralResponse.ok
      ? await centralResponse.json()
      : null;
    setCentralStatus(central);
    const localSecurityEnabled = Boolean(capabilities?.local_security_controls_enabled) && !Boolean(central?.enforced);
    setLocalControls(localSecurityEnabled);

    if (!localSecurityEnabled) {
      setSessions([]);
      return;
    }

    const sessionResponse = await apiFetch("/auth/sessions", { cache: "no-store" });
    if (sessionResponse.ok) setSessions(await sessionResponse.json());
  }

  useEffect(() => {
    void load();
  }, []);

  async function setupMfa() {
    const response = await apiFetch("/auth/mfa/setup", { method: "POST" });
    if (!response.ok) {
      setToast("Unable to start MFA setup");
      return;
    }
    const data = await response.json();
    setSecret(data.secret);
    setUri(data.provisioning_uri);
  }

  async function enableMfa() {
    const response = await apiFetch("/auth/mfa/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (response.ok) {
      setToast("MFA enabled. Sign in again to continue.");
      setTimeout(() => router.replace("/login"), 900);
    } else {
      setToast("Invalid authenticator code");
    }
  }

  async function revoke(id: string) {
    await apiFetch(`/auth/sessions/${id}`, { method: "DELETE" });
    setToast("Session revoked");
    await load();
  }

  async function revokeEverywhere() {
    await apiFetch("/auth/sessions", { method: "DELETE" });
    router.replace("/login");
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = String(form.get("new_password") || "");
    if (next !== String(form.get("confirm_password") || "")) {
      setToast("New passwords do not match");
      return;
    }
    const response = await apiFetch("/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: form.get("current_password"),
        new_password: next,
      }),
    });
    if (response.ok) {
      setToast("Password changed. Sign in again.");
      setTimeout(() => router.replace("/login"), 900);
    } else {
      const body = await response.json().catch(() => ({}));
      setToast(String(body.detail || "Unable to change password"));
    }
  }

  return (
    <ControlShell
      title="Security"
      subtitle="MFA, password and authenticated device controls"
      userEmail={me?.email}
    >
      <div className="space-y-4">
        <PageHeader
          eyebrow="Identity protection"
          title="Security centre"
          description={
            localControls
              ? "Protect privileged infrastructure access with authenticator MFA, strong passwords and revocable refresh sessions."
              : "This deployment uses Ithute central authentication. Identity security is managed by the central Ithute account service."
          }
          actions={
            <StatusBadge state={localControls ? (me?.mfa_enabled ? "good" : "warn") : "good"}>
              {localControls ? (me?.mfa_enabled ? "MFA enabled" : "MFA recommended") : "Central auth"}
            </StatusBadge>
          }
        />

        {centralStatus?.enabled ? (
          <section className="surface-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]">
                  <ShieldCheck size={20} />
                </div>
                <div>
                  <p className="text-sm font-black">Permanent Central Authentication</p>
                  <p className="mt-1 max-w-2xl text-[11px] leading-5 text-[var(--admin-muted)]">
                    This is an account-level backend policy. Once enabled, password login is blocked and every device must use Ithute Central Authentication. It cannot be switched off.
                  </p>
                </div>
              </div>
              <button
                type="button"
                aria-pressed={Boolean(centralStatus.enforced)}
                disabled={centralStatus.enforced}
                onClick={() => {
                  if (!centralStatus.enforced) window.location.assign(`${API}/auth/ithute/enroll`);
                }}
                className={`relative h-7 w-12 shrink-0 rounded-full transition ${centralStatus.enforced ? "cursor-not-allowed bg-emerald-600" : "bg-slate-300 hover:bg-slate-400"}`}
                title={centralStatus.enforced ? "Central Authentication is permanently locked on" : "Permanently enable Central Authentication"}
              >
                <span className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition ${centralStatus.enforced ? "left-6" : "left-1"}`} />
              </button>
            </div>
            {centralStatus.enforced ? (
              <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-[11px] font-bold text-emerald-800">
                Locked on permanently{centralStatus.enforced_at ? ` · enabled ${new Date(centralStatus.enforced_at).toLocaleString()}` : ""}. This state is stored on the server and follows the account to every device.
              </div>
            ) : (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <a className="btn-primary" href={`${API}/auth/ithute/enroll`}>
                  Enable permanently
                </a>
                <p className="text-[10px] leading-5 text-[var(--admin-muted)]">
                  You will confirm your Ithute Identity before the backend locks this policy on.
                </p>
              </div>
            )}
          </section>
        ) : null}

        {!localControls ? (
          <section className="surface-card p-5">
            <div className="flex items-start gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-700">
                <ShieldCheck size={20} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-black">Managed by Ithute central authentication</p>
                <p className="mt-1 max-w-2xl text-[11px] leading-5 text-[var(--admin-muted)]">
                  Manage active product sessions, trusted devices, MFA and recovery codes, passkeys, password security and recent security activity from the central identity service.
                </p>
                <a
                  className="btn-primary mt-4 inline-flex"
                  href={`${API}/auth/ithute/account`}
                >
                  <ExternalLink size={14} />
                  Open central security center
                </a>
              </div>
            </div>
          </section>
        ) : (
          <>
            <section className="grid gap-4 xl:grid-cols-2">
              <div className="surface-card p-4 sm:p-5">
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]">
                    <Smartphone size={18} />
                  </div>
                  <div>
                    <p className="text-sm font-black">Authenticator MFA</p>
                    <p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Use a TOTP authenticator to add a second factor to sign-in.</p>
                  </div>
                </div>
                {me?.mfa_enabled ? (
                  <div className="mt-4 rounded-xl bg-emerald-50 p-4 text-[11px] font-bold text-emerald-700">
                    <ShieldCheck size={15} className="mr-2 inline" />
                    Authenticator MFA is active for this account.
                  </div>
                ) : (
                  <div className="mt-4">
                    <button className="btn-primary" onClick={() => void setupMfa()}>
                      <KeyRound size={14} />
                      Set up authenticator
                    </button>
                    {secret ? (
                      <div className="mt-4 rounded-xl border border-[var(--admin-line)] bg-[#f8faf8] p-4">
                        <p className="label">Secret</p>
                        <code className="block break-all rounded-lg bg-white p-2 text-[10px]">{secret}</code>
                        <p className="mt-3 label">Provisioning URI</p>
                        <code className="block max-h-20 overflow-auto break-all rounded-lg bg-white p-2 text-[9px]">{uri}</code>
                        <div className="mt-3">
                          <label className="label">6-digit code</label>
                          <input className="input" value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" maxLength={6} placeholder="123456" />
                          <button className="btn-primary mt-3" onClick={() => void enableMfa()}>Enable MFA</button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>

              <form onSubmit={changePassword} className="surface-card p-4 sm:p-5">
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]">
                    <LockKeyhole size={18} />
                  </div>
                  <div>
                    <p className="text-sm font-black">Change password</p>
                    <p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Changing your password invalidates active sessions for security.</p>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  <div><label className="label">Current password</label><input className="input" type="password" name="current_password" required autoComplete="current-password" /></div>
                  <div><label className="label">New password</label><input className="input" type="password" name="new_password" required minLength={12} autoComplete="new-password" /></div>
                  <div><label className="label">Confirm new password</label><input className="input" type="password" name="confirm_password" required minLength={12} autoComplete="new-password" /></div>
                  <button className="btn-primary">Change password</button>
                </div>
              </form>
            </section>

            <section className="surface-card p-4 sm:p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-black">Signed-in devices</p>
                  <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Review refresh sessions and revoke devices you no longer trust.</p>
                </div>
                <button className="btn-danger" onClick={() => { setRevokeAll(true); setConfirm(""); }}>
                  <Trash2 size={14} />
                  Sign out everywhere
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {sessions.length ? sessions.map((session) => (
                  <div key={session.id} className="flex flex-col gap-3 rounded-xl border border-[var(--admin-line)] p-4 md:flex-row md:items-center">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#f3f6f4] text-[var(--admin-pine)]"><Laptop size={17} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-[11px] font-black">{session.user_agent || "Unknown client"}</p>
                        <StatusBadge state={session.revoked ? "neutral" : "good"}>{session.revoked ? "Revoked" : "Active"}</StatusBadge>
                      </div>
                      <p className="mt-1 text-[9px] text-[var(--admin-muted)]">
                        IP {session.ip_address || "unknown"} · created {new Date(session.created_at).toLocaleString()} · expires {new Date(session.expires_at).toLocaleString()}
                      </p>
                    </div>
                    {!session.revoked ? <button className="btn-secondary" onClick={() => void revoke(session.id)}>Revoke</button> : null}
                  </div>
                )) : <EmptyState title="No sessions" description="No refresh sessions are currently registered for this account." />}
              </div>
            </section>
          </>
        )}
      </div>

      {localControls ? (
        <ConfirmDialog
          open={revokeAll}
          title="Sign out everywhere"
          description="This revokes all refresh sessions and invalidates the current session. You will need to sign in again on every device."
          dangerous
          confirmLabel="Revoke all sessions"
          requireText="SIGN OUT"
          value={confirm}
          onValueChange={setConfirm}
          onCancel={() => setRevokeAll(false)}
          onConfirm={() => void revokeEverywhere()}
        />
      ) : null}

      {toast ? (
        <Toast
          tone={toast.toLowerCase().includes("unable") || toast.toLowerCase().includes("invalid") ? "error" : "success"}
          message={toast}
          onClose={() => setToast("")}
        />
      ) : null}
    </ControlShell>
  );
}
