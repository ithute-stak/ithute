"use client";

import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Cloud,
  ExternalLink,
  Inbox,
  Loader2,
  Mail,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { API } from "../mail-types";

type OAuthCapability = {
  provider: string;
  name: string;
  configured: boolean;
  imap_host: string;
  smtp_host: string;
};

type ConnectedAccount = {
  id: string;
  provider: string;
  address: string;
  display_name: string;
  auth_type: string;
  status: string;
  sync_enabled: boolean;
  last_connected_at?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
};

type AccountsPayload = {
  hosted: { address: string; display_name: string; type: "hosted" };
  items: ConnectedAccount[];
};

async function mailApi(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function providerLabel(value: string) {
  const key = value.toLowerCase();
  if (key === "google") return "Google / Gmail";
  if (key === "microsoft") return "Microsoft 365 / Outlook";
  if (key === "yahoo") return "Yahoo Mail";
  if (key === "icloud") return "Apple iCloud Mail";
  if (key === "zoho") return "Zoho Mail";
  if (key === "fastmail") return "Fastmail";
  return "External mail";
}

function providerMark(value: string) {
  const key = value.toLowerCase();
  if (key === "google") return "G";
  if (key === "microsoft") return "M";
  if (key === "yahoo") return "Y";
  if (key === "icloud") return "iC";
  if (key === "zoho") return "Z";
  return "@";
}

export default function MailAccountsPage() {
  const [accounts, setAccounts] = useState<AccountsPayload | null>(null);
  const [oauth, setOauth] = useState<OAuthCapability[]>([]);
  const [temporaryExternal, setTemporaryExternal] = useState<{ address: string; display_name?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [accountResponse, capabilityResponse, externalResponse] = await Promise.all([
        mailApi("/connected-accounts"),
        mailApi("/connected-accounts/capabilities"),
        fetch(`${API}/webmail/external/session`, { credentials: "include" }),
      ]);
      if (accountResponse.status === 401) {
        window.location.assign("/webmail");
        return;
      }
      if (!accountResponse.ok) throw new Error("Unable to load connected mail accounts");
      setAccounts(await accountResponse.json());
      if (capabilityResponse.ok) {
        const payload = await capabilityResponse.json();
        setOauth(payload.oauth || []);
      }
      if (externalResponse.ok) {
        const payload = await externalResponse.json();
        setTemporaryExternal({ address: String(payload.address || ""), display_name: String(payload.display_name || "") });
      } else {
        setTemporaryExternal(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load mail accounts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const oauthError = params.get("oauth_error");
    if (connected) setNotice(`${connected} is now connected to iMail.`);
    if (oauthError) setError(oauthError);
  }, [refresh]);

  const connectedAddresses = useMemo(
    () => new Set((accounts?.items || []).map((item) => item.address.toLowerCase())),
    [accounts],
  );

  async function startOauth(provider: string) {
    setBusy(`oauth:${provider}`);
    setError("");
    try {
      const response = await mailApi(`/connected-accounts/oauth/${encodeURIComponent(provider)}/start`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to start secure provider sign-in");
      window.location.assign(payload.authorization_url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start provider sign-in");
      setBusy("");
    }
  }

  async function rememberExternal() {
    if (!temporaryExternal) return;
    setBusy("remember");
    setError("");
    try {
      const response = await mailApi("/connected-accounts/from-external-session", {
        method: "POST",
        body: JSON.stringify({ label: temporaryExternal.display_name || "", sync_enabled: true }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to save this external mailbox");
      setNotice(`${temporaryExternal.address} will now remain available in iMail.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save external mailbox");
    } finally {
      setBusy("");
    }
  }

  async function verifyAccount(id: string) {
    setBusy(`verify:${id}`);
    setError("");
    try {
      const response = await mailApi(`/connected-accounts/${id}/verify`, { method: "POST", body: "{}" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Connection check failed");
      setNotice("Mailbox connection verified successfully.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connection check failed");
    } finally {
      setBusy("");
    }
  }

  async function removeAccount(item: ConnectedAccount) {
    if (!window.confirm(`Remove ${item.address} from iMail? Messages at the provider will not be deleted.`)) return;
    setBusy(`remove:${item.id}`);
    setError("");
    try {
      const response = await mailApi(`/connected-accounts/${item.id}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to remove connected account");
      }
      setNotice(`${item.address} was disconnected. No provider messages were deleted.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to remove connected account");
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="min-h-screen bg-[#f6f8fc] text-[#202124] dark:bg-[#0f1418] dark:text-slate-100">
      <header className="sticky top-0 z-20 flex min-h-16 items-center justify-between gap-4 border-b border-[#e2e6ea] bg-white/95 px-4 backdrop-blur dark:border-white/10 dark:bg-[#111820]/95 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/webmail" className="grid h-9 w-9 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10" aria-label="Back to iMail"><ArrowLeft size={19} /></Link>
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#0c6f55] text-sm font-bold text-white">iM</span>
          <div className="min-w-0"><h1 className="truncate text-base font-semibold">Mail accounts</h1><p className="truncate text-xs text-[#6b7280] dark:text-slate-400">One iMail workspace for business, Gmail, Outlook and other providers</p></div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => void refresh()} className="grid h-9 w-9 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={17} /></button>
          <Link href="/webmail/unified" className="hidden rounded-full bg-[#0b57d0] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#0847ad] sm:inline-flex">Open unified inbox</Link>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-6xl gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_330px]">
        <section className="space-y-5">
          {error ? <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200"><TriangleAlert className="mt-0.5 shrink-0" size={17} /><span>{error}</span></div> : null}
          {notice ? <div className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200"><CheckCircle2 className="mt-0.5 shrink-0" size={17} /><span>{notice}</span></div> : null}

          <div className="rounded-3xl border border-[#e2e6ea] bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#141b20] sm:p-6">
            <div className="mb-5 flex items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Your mailboxes</h2><p className="mt-1 text-sm text-[#6b7280] dark:text-slate-400">Switch between accounts or read them together in Unified Inbox.</p></div><Mail size={22} className="text-[#0b57d0]" /></div>
            {loading ? <div className="grid min-h-44 place-items-center"><Loader2 className="animate-spin text-[#0b57d0]" size={26} /></div> : (
              <div className="space-y-3">
                {accounts?.hosted ? (
                  <div className="flex flex-col gap-3 rounded-2xl border border-[#dce4ee] bg-[#f8fbff] p-4 sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/[.035]">
                    <div className="flex min-w-0 items-center gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#0c6f55] text-sm font-bold text-white">iM</span><div className="min-w-0"><div className="flex items-center gap-2"><p className="truncate font-semibold">{accounts.hosted.display_name || accounts.hosted.address}</p><span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">Hosted</span></div><p className="truncate text-sm text-[#6b7280] dark:text-slate-400">{accounts.hosted.address}</p></div></div>
                    <Link href="/webmail" className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#d2dae4] px-3 py-2 text-sm font-semibold hover:bg-white dark:border-white/10 dark:hover:bg-white/5">Open mailbox <ExternalLink size={15} /></Link>
                  </div>
                ) : null}
                {(accounts?.items || []).map((item) => (
                  <div key={item.id} className="flex flex-col gap-3 rounded-2xl border border-[#e1e5ea] p-4 sm:flex-row sm:items-center sm:justify-between dark:border-white/10">
                    <div className="flex min-w-0 items-center gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#eef3f9] text-sm font-bold text-[#35506e] dark:bg-white/10 dark:text-slate-200">{providerMark(item.provider)}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="truncate font-semibold">{item.display_name || item.address}</p><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${item.status === "active" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"}`}>{item.status.replaceAll("_", " ")}</span></div><p className="truncate text-sm text-[#6b7280] dark:text-slate-400">{item.address} · {providerLabel(item.provider)} · {item.auth_type === "oauth" ? "OAuth" : "Secure credential"}</p>{item.last_error ? <p className="mt-1 line-clamp-2 text-xs text-amber-700 dark:text-amber-300">{item.last_error}</p> : null}</div></div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2"><Link href={`/webmail/unified?account=${encodeURIComponent(item.id)}`} className="rounded-xl bg-[#edf3fe] px-3 py-2 text-sm font-semibold text-[#174ea6] hover:bg-[#e1ebfc] dark:bg-blue-950/40 dark:text-blue-200">View mail</Link><button onClick={() => void verifyAccount(item.id)} disabled={busy === `verify:${item.id}`} className="grid h-9 w-9 place-items-center rounded-xl border border-[#d2dae4] text-[#5f6368] hover:bg-[#f5f7fa] disabled:opacity-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5" title="Check connection">{busy === `verify:${item.id}` ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}</button><button onClick={() => void removeAccount(item)} disabled={busy === `remove:${item.id}`} className="grid h-9 w-9 place-items-center rounded-xl border border-[#d2dae4] text-[#7a4b4b] hover:bg-red-50 disabled:opacity-50 dark:border-white/10 dark:text-red-300 dark:hover:bg-red-950/30" title="Disconnect">{busy === `remove:${item.id}` ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}</button></div>
                  </div>
                ))}
                {!accounts?.items?.length ? <div className="rounded-2xl border border-dashed border-[#cfd8e3] px-5 py-8 text-center dark:border-white/15"><Cloud className="mx-auto mb-3 text-[#7b8794]" size={28} /><p className="font-semibold">No persistent external accounts yet</p><p className="mx-auto mt-1 max-w-md text-sm text-[#6b7280] dark:text-slate-400">Connect Google, Microsoft or save a verified external mailbox below. Your Ithute-hosted mailbox remains available independently.</p></div> : null}
              </div>
            )}
          </div>

          <div className="rounded-3xl border border-[#e2e6ea] bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#141b20] sm:p-6">
            <div className="mb-5"><h2 className="text-lg font-semibold">Connect another account</h2><p className="mt-1 text-sm text-[#6b7280] dark:text-slate-400">OAuth connections never expose your Google or Microsoft password to iMail.</p></div>
            <div className="grid gap-3 sm:grid-cols-2">
              {oauth.map((item) => (
                <button key={item.provider} onClick={() => void startOauth(item.provider)} disabled={!item.configured || busy === `oauth:${item.provider}`} className="flex items-center gap-3 rounded-2xl border border-[#dce2e9] p-4 text-left transition hover:border-[#9db7dd] hover:bg-[#f8fbff] disabled:cursor-not-allowed disabled:opacity-55 dark:border-white/10 dark:hover:bg-white/5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef3f9] font-bold text-[#35506e] dark:bg-white/10 dark:text-slate-200">{providerMark(item.provider)}</span><span className="min-w-0 flex-1"><span className="block font-semibold">Continue with {item.provider === "google" ? "Google" : "Microsoft"}</span><span className="block text-xs text-[#6b7280] dark:text-slate-400">{item.configured ? "Secure OAuth · IMAP + SMTP" : "Administrator configuration required"}</span></span>{busy === `oauth:${item.provider}` ? <Loader2 size={17} className="animate-spin" /> : <ExternalLink size={16} className="text-[#7b8794]" />}
                </button>
              ))}
              <Link href="/webmail/external" className="flex items-center gap-3 rounded-2xl border border-[#dce2e9] p-4 transition hover:border-[#9db7dd] hover:bg-[#f8fbff] dark:border-white/10 dark:hover:bg-white/5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef3f9] text-[#35506e] dark:bg-white/10 dark:text-slate-200"><Plus size={18} /></span><span className="min-w-0 flex-1"><span className="block font-semibold">Other email account</span><span className="block text-xs text-[#6b7280] dark:text-slate-400">Automatic provider detection or secure IMAP/SMTP</span></span><ExternalLink size={16} className="text-[#7b8794]" /></Link>
            </div>
            {temporaryExternal && !connectedAddresses.has(temporaryExternal.address.toLowerCase()) ? <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-emerald-900/50 dark:bg-emerald-950/20"><div><p className="font-semibold text-emerald-900 dark:text-emerald-200">Save {temporaryExternal.address} to iMail?</p><p className="text-sm text-emerald-700 dark:text-emerald-300/80">This external session is verified. Saving it makes the account available in Unified Inbox and after browser restarts.</p></div><button onClick={() => void rememberExternal()} disabled={busy === "remember"} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50">{busy === "remember" ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />} Save account</button></div> : null}
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-3xl border border-[#e2e6ea] bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#141b20]"><h3 className="font-semibold">Next-generation iMail</h3><div className="mt-4 space-y-3 text-sm text-[#5f6368] dark:text-slate-300"><div className="flex gap-2"><Inbox size={16} className="mt-0.5 shrink-0 text-[#0b57d0]" /><span><strong className="text-[#202124] dark:text-white">Unified Inbox</strong><br />Read hosted and connected accounts together.</span></div><div className="flex gap-2"><ShieldCheck size={16} className="mt-0.5 shrink-0 text-emerald-700" /><span><strong className="text-[#202124] dark:text-white">Protected credentials</strong><br />Stored secrets and OAuth tokens are encrypted.</span></div><div className="flex gap-2"><Cloud size={16} className="mt-0.5 shrink-0 text-[#7356a8]" /><span><strong className="text-[#202124] dark:text-white">Migration center</strong><br />Copy Gmail or external mail into your business mailbox without deleting the source.</span></div></div><div className="mt-5 grid gap-2"><Link href="/webmail/unified" className="rounded-xl bg-[#0b57d0] px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-[#0847ad]">Open Unified Inbox</Link><Link href="/webmail/migrate" className="rounded-xl border border-[#d2dae4] px-4 py-2.5 text-center text-sm font-semibold hover:bg-[#f5f7fa] dark:border-white/10 dark:hover:bg-white/5">Migration center</Link></div></div>
        </aside>
      </div>
    </main>
  );
}
