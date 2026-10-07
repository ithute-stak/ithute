"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, ExternalLink, Fingerprint, KeyRound, Laptop, LockKeyhole, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { ConfirmDialog, EmptyState, PageHeader, StatusBadge, Toast } from "@/components/ui-kit";
import { apiFetch } from "@/lib/platform-api";
import { registrationCredentialToJSON, registrationOptionsFromJSON } from "@/lib/passkeys";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Session = {
  id: string;
  created_at: string;
  expires_at: string;
  user_agent?: string;
  ip_address?: string;
  revoked: boolean;
  trusted_device_id?: string | null;
  risk_score?: number;
  risk_level?: string;
  new_device?: boolean;
  last_seen_at?: string | null;
};

type TrustedDevice = {
  id: string;
  label?: string | null;
  first_seen_at: string;
  last_seen_at: string;
  first_ip_address?: string | null;
  last_ip_address?: string | null;
  first_user_agent?: string | null;
  trusted: boolean;
  revoked: boolean;
};

type Passkey = {
  id: string;
  name: string;
  created_at: string;
  last_used_at?: string | null;
  device_type?: string | null;
  backed_up: boolean;
  revoked: boolean;
};

type SecurityEvent = {
  id: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
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
  const [devices, setDevices] = useState<TrustedDevice[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [passkeys, setPasskeys] = useState<Passkey[]>([]);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [recoveryRemaining, setRecoveryRemaining] = useState(0);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
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
      setDevices([]);
      setEvents([]);
      setPasskeys([]);
      return;
    }

    const [sessionResponse, deviceResponse, recoveryResponse, eventResponse, passkeyResponse] = await Promise.all([
      apiFetch("/auth/sessions", { cache: "no-store" }),
      apiFetch("/auth/devices", { cache: "no-store" }),
      apiFetch("/auth/recovery-codes", { cache: "no-store" }),
      apiFetch("/auth/security-events", { cache: "no-store" }),
      apiFetch("/auth/passkeys", { cache: "no-store" }),
    ]);
    if (sessionResponse.ok) setSessions(await sessionResponse.json());
    if (deviceResponse.ok) setDevices(await deviceResponse.json());
    if (recoveryResponse.ok) setRecoveryRemaining(Number((await recoveryResponse.json()).remaining || 0));
    if (eventResponse.ok) setEvents(await eventResponse.json());
    if (passkeyResponse.ok) setPasskeys(await passkeyResponse.json());
  }

  useEffect(() => {
    void load();
  }, []);

  async function addPasskey() {
    setToast("");
    if (!window.PublicKeyCredential || !navigator.credentials) {
      setToast("This browser does not support passkeys.");
      return;
    }
    setPasskeyBusy(true);
    try {
      const optionsResponse = await apiFetch("/auth/passkeys/register/options", { method: "POST" });
      if (!optionsResponse.ok) {
        const body = await optionsResponse.json().catch(() => ({}));
        throw new Error(String(body.detail || "Unable to start passkey registration"));
      }
      const payload = await optionsResponse.json();
      const credential = await navigator.credentials.create({
        publicKey: registrationOptionsFromJSON(payload.publicKey),
      }) as PublicKeyCredential | null;
      if (!credential) throw new Error("No passkey was created.");

      const response = await apiFetch("/auth/passkeys/register/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          flow_id: payload.flow_id,
          name: "Passkey",
          credential: registrationCredentialToJSON(credential),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(String(body.detail || "Unable to verify the passkey"));
      }
      setToast("Passkey added. You can now sign in without your password on supported devices.");
      await load();
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "NotAllowedError") {
        setToast("Passkey setup was cancelled or timed out.");
      } else {
        setToast(cause instanceof Error ? cause.message : "Unable to add passkey");
      }
    } finally {
      setPasskeyBusy(false);
    }
  }

  async function revokePasskey(id: string) {
    const response = await apiFetch(`/auth/passkeys/${id}`, { method: "DELETE" });
    if (response.ok) {
      setToast("Passkey revoked");
      await load();
    } else {
      setToast("Unable to revoke passkey");
    }
  }

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


  async function generateRecoveryCodes() {
    const response = await apiFetch("/auth/recovery-codes/regenerate", { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setToast(String(body.detail || "Unable to generate recovery codes"));
      return;
    }
    const data = await response.json();
    setRecoveryCodes(data.codes || []);
    setRecoveryRemaining(Number(data.remaining || 0));
    setToast("New recovery codes generated. Save them now; they are shown only once.");
    await load();
  }

  async function trustDevice(id: string) {
    const response = await apiFetch(`/auth/devices/${id}/trust`, { method: "POST" });
    if (response.ok) {
      setToast("Device marked as trusted");
      await load();
    }
  }

  async function revokeDevice(id: string) {
    const response = await apiFetch(`/auth/devices/${id}`, { method: "DELETE" });
    if (response.ok) {
      setToast("Device revoked");
      await load();
    }
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
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]"><Fingerprint size={18} /></div>
                  <div>
                    <p className="text-sm font-black">Passkeys</p>
                    <p className="mt-1 max-w-2xl text-[10px] leading-5 text-[var(--admin-muted)]">Phishing-resistant sign-in using your device biometrics, PIN or security key. Biometric data stays on your device.</p>
                  </div>
                </div>
                <button className="btn-primary" disabled={passkeyBusy} onClick={() => void addPasskey()}>
                  <Fingerprint size={14} />
                  {passkeyBusy ? "Waiting for device…" : "Add passkey"}
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {passkeys.length ? passkeys.map((passkey) => (
                  <div key={passkey.id} className="flex flex-col gap-3 rounded-xl border border-[var(--admin-line)] p-4 md:flex-row md:items-center">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#f3f6f4] text-[var(--admin-pine)]"><Fingerprint size={17} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-[11px] font-black">{passkey.name}</p>
                        <StatusBadge state={passkey.revoked ? "neutral" : "good"}>{passkey.revoked ? "Revoked" : "Active"}</StatusBadge>
                        {passkey.backed_up ? <StatusBadge state="good">Synced</StatusBadge> : null}
                      </div>
                      <p className="mt-1 text-[9px] text-[var(--admin-muted)]">Added {new Date(passkey.created_at).toLocaleString()}{passkey.last_used_at ? ` · last used ${new Date(passkey.last_used_at).toLocaleString()}` : ""}{passkey.device_type ? ` · ${passkey.device_type.replaceAll("_", " ")}` : ""}</p>
                    </div>
                    {!passkey.revoked ? <button className="btn-danger" onClick={() => void revokePasskey(passkey.id)}>Revoke</button> : null}
                  </div>
                )) : <EmptyState title="No passkeys yet" description="Add a passkey to get phishing-resistant passwordless sign-in." />}
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className="surface-card p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-black">Recovery codes</p>
                    <p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">One-time backup codes for accounts protected by authenticator MFA.</p>
                  </div>
                  <StatusBadge state={recoveryRemaining > 2 ? "good" : recoveryRemaining ? "warn" : "neutral"}>{recoveryRemaining} remaining</StatusBadge>
                </div>
                <button className="btn-secondary mt-4" disabled={!me?.mfa_enabled} onClick={() => void generateRecoveryCodes()}>
                  <KeyRound size={14} />
                  {recoveryRemaining ? "Regenerate codes" : "Generate codes"}
                </button>
                {!me?.mfa_enabled ? <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Enable MFA before generating recovery codes.</p> : null}
                {recoveryCodes.length ? (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <p className="text-[10px] font-black text-amber-900">Save these codes now. Ithute will not show them again.</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px] font-bold text-amber-950">
                      {recoveryCodes.map((value) => <code key={value} className="rounded-lg bg-white px-2 py-1.5">{value}</code>)}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="surface-card p-4 sm:p-5">
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]"><Activity size={18} /></div>
                  <div>
                    <p className="text-sm font-black">Adaptive sign-in protection</p>
                    <p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Every login is scored from device familiarity, network changes, client changes and verified MFA.</p>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Devices</p><p className="mt-1 text-xl font-black">{devices.filter((d) => !d.revoked).length}</p></div>
                  <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Trusted</p><p className="mt-1 text-xl font-black">{devices.filter((d) => d.trusted && !d.revoked).length}</p></div>
                  <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">New alerts</p><p className="mt-1 text-xl font-black">{events.filter((e) => e.action === "auth.device.new").length}</p></div>
                </div>
              </div>
            </section>

            <section className="surface-card p-4 sm:p-5">
              <div>
                <p className="text-sm font-black">Trusted devices</p>
                <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Device trust is stored by the backend and survives browser refreshes and session rotation.</p>
              </div>
              <div className="mt-4 space-y-2">
                {devices.length ? devices.map((device) => (
                  <div key={device.id} className="flex flex-col gap-3 rounded-xl border border-[var(--admin-line)] p-4 md:flex-row md:items-center">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#f3f6f4] text-[var(--admin-pine)]"><Laptop size={17} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-[11px] font-black">{device.label || device.first_user_agent || "Unknown device"}</p>
                        <StatusBadge state={device.revoked ? "neutral" : device.trusted ? "good" : "warn"}>{device.revoked ? "Revoked" : device.trusted ? "Trusted" : "Untrusted"}</StatusBadge>
                      </div>
                      <p className="mt-1 text-[9px] text-[var(--admin-muted)]">Last IP {device.last_ip_address || "unknown"} · last seen {new Date(device.last_seen_at).toLocaleString()}</p>
                    </div>
                    {!device.revoked ? <div className="flex gap-2">{!device.trusted ? <button className="btn-secondary" onClick={() => void trustDevice(device.id)}>Trust</button> : null}<button className="btn-danger" onClick={() => void revokeDevice(device.id)}>Revoke</button></div> : null}
                  </div>
                )) : <EmptyState title="No devices yet" description="Devices will appear here after successful sign-ins." />}
              </div>
            </section>

            <section className="surface-card p-4 sm:p-5">
              <div>
                <p className="text-sm font-black">Security event history</p>
                <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Recent authentication and account-security activity recorded by the backend.</p>
              </div>
              <div className="mt-4 space-y-2">
                {events.length ? events.slice(0, 20).map((event) => (
                  <div key={event.id} className="flex items-center gap-3 rounded-xl border border-[var(--admin-line)] px-4 py-3">
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#eef4f1] text-[var(--admin-pine)]"><Activity size={15} /></div>
                    <div className="min-w-0 flex-1"><p className="truncate text-[11px] font-black">{event.action.replaceAll(".", " ")}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{new Date(event.created_at).toLocaleString()} · {event.resource_type}</p></div>
                    {typeof event.metadata?.risk_score === "number" ? <StatusBadge state={Number(event.metadata.risk_score) >= 50 ? "warn" : "good"}>Risk {String(event.metadata.risk_score)}</StatusBadge> : null}
                  </div>
                )) : <EmptyState title="No security events" description="Authentication activity will appear here as it occurs." />}
              </div>
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
                        {session.new_device ? <StatusBadge state="warn">New device</StatusBadge> : null}
                        {session.risk_level ? <StatusBadge state={(session.risk_score || 0) >= 50 ? "warn" : "good"}>Risk {session.risk_score || 0}/100</StatusBadge> : null}
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
