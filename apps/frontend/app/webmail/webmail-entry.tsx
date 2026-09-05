"use client";

import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  BellRing,
  Boxes,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Landmark,
  Loader2,
  LockKeyhole,
  Mail,
  MonitorSmartphone,
  Network,
  ShieldCheck,
  ShoppingCart,
  UserRound,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { MailClient } from "./mail-client";
import { API, webmail } from "./mail-types";

type LoginMode = "mailbox" | "system";
type SessionState = "checking" | "guest" | "mailbox";

const products = [
  {
    name: "Mailbox",
    description: "Professional business email with secure hosted mailboxes.",
    icon: Mail,
  },
  {
    name: "LoanHub",
    description: "Lending operations, borrower workflows, approvals and tracking.",
    icon: Landmark,
  },
  {
    name: "!THUTE Auth",
    description: "Central identity, secure sessions and application authentication.",
    icon: LockKeyhole,
  },
  {
    name: "!THUTE Push",
    description: "Real-time notification delivery across supported devices.",
    icon: BellRing,
  },
  {
    name: "RSL POS",
    description: "Modern point-of-sale tools for retail and branch operations.",
    icon: ShoppingCart,
  },
];

const benefits = [
  { title: "Connected services", detail: "A growing business platform", icon: Boxes },
  { title: "Business email", detail: "Hosted mail under your own domain", icon: Mail },
  { title: "Secure access", detail: "Modern authentication controls", icon: ShieldCheck },
  { title: "Live notifications", detail: "Push-ready platform services", icon: BellRing },
  { title: "Works everywhere", detail: "Desktop and mobile-ready interfaces", icon: MonitorSmartphone },
];

export function WebmailEntry() {
  const [sessionState, setSessionState] = useState<SessionState>("checking");
  const [mode, setMode] = useState<LoginMode>("mailbox");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mailboxAddress, setMailboxAddress] = useState("");
  const [mailboxPassword, setMailboxPassword] = useState("");
  const [systemEmail, setSystemEmail] = useState("");
  const [systemPassword, setSystemPassword] = useState("");
  const [systemMfaCode, setSystemMfaCode] = useState("");
  const [systemMfaRequired, setSystemMfaRequired] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await webmail("/session");
        if (!active) return;
        setSessionState(response.ok ? "mailbox" : "guest");
      } catch {
        if (active) setSessionState("guest");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  function selectMode(nextMode: LoginMode) {
    setMode(nextMode);
    setError("");
    setShowPassword(false);
    if (nextMode === "mailbox") {
      setSystemMfaRequired(false);
      setSystemMfaCode("");
    }
  }

  async function mailboxLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await webmail("/session", {
        method: "POST",
        body: JSON.stringify({ address: mailboxAddress.trim(), password: mailboxPassword }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(String(body.detail || "Mailbox login failed. Check the mailbox address and password."));
        return;
      }
      setSessionState("mailbox");
    } catch {
      setError("The mail service could not be reached. Please try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  async function systemLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: systemEmail.trim(),
          password: systemPassword,
          ...(systemMfaCode.trim() ? { mfa_code: systemMfaCode.replace(/\s/g, "").trim() } : {}),
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = String(body.detail || "We could not sign you in with those credentials.");
        const normalized = detail.toLowerCase();
        if (normalized.includes("mfa code required")) {
          setSystemMfaRequired(true);
          setError("");
        } else if (normalized.includes("invalid mfa")) {
          setSystemMfaRequired(true);
          setError("That authentication code was not accepted. Check your authenticator app and try again.");
        } else if (response.status === 401) {
          setError("The email address or password is incorrect.");
        } else if (response.status === 429) {
          setError("Too many sign-in attempts. Please wait a moment before trying again.");
        } else {
          setError(detail);
        }
        return;
      }

      window.location.assign("/dashboard");
    } catch {
      setError("The secure control plane could not be reached. Please try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  if (sessionState === "checking") {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f3f7f5]">
        <div className="flex items-center gap-3 rounded-2xl border border-[#dfe8e3] bg-white px-5 py-4 text-sm font-semibold text-[#345047] shadow-sm">
          <Loader2 className="animate-spin text-[#1d5d50]" size={18} />
          Opening !THUTE Mail
        </div>
      </div>
    );
  }

  if (sessionState === "mailbox") return <MailClient />;

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f2f7f5] px-4 py-5 text-[#172a25] sm:px-6 sm:py-8 lg:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_8%_8%,rgba(52,122,102,.10),transparent_28%),radial-gradient(circle_at_91%_14%,rgba(216,197,106,.13),transparent_25%),linear-gradient(180deg,#f7faf9_0%,#eef5f2_100%)]" />
      <div className="pointer-events-none absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(28,86,73,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(28,86,73,.035)_1px,transparent_1px)] [background-size:44px_44px]" />

      <div className="relative mx-auto grid min-h-[calc(100vh-2.5rem)] w-full max-w-[1380px] overflow-hidden rounded-[30px] border border-[#dce7e2] bg-white shadow-[0_32px_90px_rgba(28,64,52,.12)] lg:grid-cols-[1.48fr_.92fr]">
        <section className="relative overflow-hidden border-b border-[#e5ece8] p-6 sm:p-9 lg:border-b-0 lg:border-r lg:p-10 xl:p-12">
          <div className="pointer-events-none absolute right-[-6rem] top-[-6rem] h-72 w-72 rounded-full bg-[#d7e9e2]/60 blur-3xl" />
          <div className="pointer-events-none absolute bottom-[-8rem] left-[20%] h-72 w-72 rounded-full bg-[#f4e9bd]/35 blur-3xl" />

          <div className="relative">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-[14px] bg-[#123a38] text-sm font-black text-[#f0d96f] shadow-[0_9px_24px_rgba(18,58,56,.18)]">!T</div>
              <div>
                <p className="text-lg font-black tracking-[.02em] text-[#143e37]">!THUTE</p>
                <p className="text-[9px] font-extrabold uppercase tracking-[.18em] text-[#799087]">Business technology platform</p>
              </div>
            </div>

            <div className="mt-8 grid items-center gap-7 xl:grid-cols-[1.05fr_.95fr]">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[#d7e6df] bg-[#f5faf8] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[.12em] text-[#397064]">
                  <Network size={13} /> Connected business services
                </div>
                <h1 className="mt-5 max-w-[610px] text-[42px] font-black leading-[.98] tracking-[-.052em] text-[#172a25] sm:text-[50px] xl:text-[58px]">
                  One platform.<br />Everything connected.
                </h1>
                <p className="mt-5 max-w-[580px] text-[17px] font-bold leading-7 text-[#286656]">
                  Email, applications and services that power your business forward.
                </p>
                <p className="mt-4 max-w-[590px] text-sm leading-7 text-[#6c7d76]">
                  !THUTE brings essential business tools together — professional mailbox hosting, lending workflows, secure authentication, notifications and point-of-sale services — with a consistent platform experience.
                </p>
              </div>

              <div className="relative mx-auto hidden h-[260px] w-full max-w-[390px] xl:block" aria-hidden="true">
                <div className="absolute inset-x-6 top-6 h-[205px] rotate-[-2deg] rounded-[28px] border border-[#d4e3dd] bg-[linear-gradient(145deg,#edf6f2,#ffffff)] shadow-[0_24px_45px_rgba(28,76,63,.15)]" />
                <div className="absolute left-10 right-2 top-3 h-[205px] rotate-[2deg] overflow-hidden rounded-[24px] border border-[#d6e2dd] bg-white shadow-[0_22px_60px_rgba(28,76,63,.17)]">
                  <div className="flex h-full">
                    <div className="w-[31%] bg-[#153f39] p-3">
                      <div className="mb-5 flex items-center gap-2 text-[8px] font-black text-[#f0d96f]"><span className="grid h-5 w-5 place-items-center rounded-md bg-white/10">!T</span> MAIL</div>
                      {["Inbox", "Sent", "Drafts", "Archive"].map((label, index) => (
                        <div key={label} className={`mb-2 h-5 rounded-md ${index === 0 ? "bg-white/16" : "bg-white/[.07]"} px-2 text-[7px] leading-5 text-white/75`}>{label}</div>
                      ))}
                    </div>
                    <div className="flex-1 p-4">
                      <div className="mb-3 h-7 rounded-lg bg-[#f0f5f3]" />
                      {[78, 92, 70, 86, 64].map((width, index) => (
                        <div key={`${width}-${index}`} className="mb-3 flex items-center gap-2">
                          <span className="h-6 w-6 rounded-full bg-[#dcebe5]" />
                          <div className="flex-1"><div className="h-2 rounded-full bg-[#d8e4df]" style={{ width: `${width}%` }} /><div className="mt-1.5 h-1.5 w-[58%] rounded-full bg-[#edf2f0]" /></div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="absolute bottom-0 left-0 grid h-16 w-16 place-items-center rounded-2xl border border-white bg-white text-[#1e765f] shadow-[0_18px_36px_rgba(26,72,59,.18)]"><Mail size={28} /></div>
                <div className="absolute bottom-[-4px] right-0 grid h-[86px] w-[86px] place-items-center rounded-[28px] border-4 border-white bg-[linear-gradient(145deg,#48a27d,#17684e)] text-white shadow-[0_20px_40px_rgba(28,105,77,.28)]"><ShieldCheck size={42} /></div>
              </div>
            </div>

            <div className="mt-9">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[.14em] text-[#6f857c]">!THUTE ecosystem</p>
                  <h2 className="mt-1 text-xl font-black tracking-[-.025em] text-[#1c342c]">Products built to work together</h2>
                </div>
                <span className="hidden text-[10px] font-bold text-[#8a9a93] sm:block">More services can be added as the platform grows.</span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                {products.map(({ name, description, icon: Icon }) => (
                  <div key={name} className="group rounded-2xl border border-[#dfe8e4] bg-white p-4 shadow-[0_8px_24px_rgba(27,67,56,.055)] transition hover:-translate-y-1 hover:border-[#bfd8cd] hover:shadow-[0_14px_30px_rgba(27,67,56,.10)]">
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#eaf5f0] text-[#1e6b56] transition group-hover:bg-[#123a38] group-hover:text-[#f0d96f]"><Icon size={18} /></div>
                    <p className="mt-3 text-[12px] font-black text-[#20372f]">{name}</p>
                    <p className="mt-1.5 text-[10px] leading-[1.55] text-[#74857d]">{description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <p className="text-[11px] font-extrabold uppercase tracking-[.14em] text-[#6f857c]">Why teams choose !THUTE</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                {benefits.map(({ title, detail, icon: Icon }) => (
                  <div key={title} className="flex gap-3 xl:block">
                    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#b8dacb] bg-[#f5fbf8] text-[#28765f]"><Icon size={15} /></div>
                    <div className="xl:mt-2.5">
                      <p className="text-[10px] font-black text-[#2e433b]">{title}</p>
                      <p className="mt-1 text-[9px] leading-4 text-[#819088]">{detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[#e6ede9] pt-5 text-[10px] font-bold text-[#788a82]">
              <span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} className="text-[#2c755f]" /> Security-first platform</span>
              <span>•</span>
              <span>Tenant-aware services</span>
              <span>•</span>
              <span>Built in Lesotho</span>
            </div>
          </div>
        </section>

        <section className="relative flex items-center bg-[#fbfdfc] p-5 sm:p-8 lg:p-9 xl:p-11">
          <div className="mx-auto w-full max-w-[460px]">
            <div className="flex items-center gap-3 lg:hidden">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#123a38] text-xs font-black text-[#f0d96f]">!T</div>
              <div><p className="font-black text-[#17372f]">!THUTE</p><p className="text-[9px] font-bold uppercase tracking-[.14em] text-[#87958f]">Connected business services</p></div>
            </div>

            <p className="mt-7 text-[11px] font-extrabold uppercase tracking-[.12em] text-[#668079] lg:mt-0">Welcome back to !THUTE</p>
            <h2 className="mt-2 text-[38px] font-black tracking-[-.045em] text-[#172a25]">{systemMfaRequired ? "Verify your account" : "Sign in"}</h2>
            <p className="mt-2 text-sm leading-6 text-[#72827a]">
              {systemMfaRequired ? "Enter the current code from your authenticator app to finish the system sign-in." : "Sign in to your mailbox or your Mailbox DNS system account."}
            </p>

            {!systemMfaRequired ? (
              <div className="mt-7 grid grid-cols-2 rounded-2xl border border-[#dce6e1] bg-[#f4f8f6] p-1">
                <button type="button" onClick={() => selectMode("mailbox")} className={`flex min-h-11 items-center justify-center gap-2 rounded-xl text-xs font-extrabold transition ${mode === "mailbox" ? "bg-white text-[#175844] shadow-sm ring-1 ring-[#d5e4dd]" : "text-[#71827a] hover:text-[#365d52]"}`}>
                  <Mail size={15} /> Mailbox Login
                </button>
                <button type="button" onClick={() => selectMode("system")} className={`flex min-h-11 items-center justify-center gap-2 rounded-xl text-xs font-extrabold transition ${mode === "system" ? "bg-white text-[#175844] shadow-sm ring-1 ring-[#d5e4dd]" : "text-[#71827a] hover:text-[#365d52]"}`}>
                  <UserRound size={15} /> System Login
                </button>
              </div>
            ) : null}

            {error ? <div role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold leading-5 text-red-700">{error}</div> : null}

            {mode === "mailbox" && !systemMfaRequired ? (
              <form onSubmit={mailboxLogin} className="mt-6 space-y-4">
                <div>
                  <label htmlFor="mailbox-address" className="mb-1.5 block text-[11px] font-extrabold text-[#31483f]">Mailbox address</label>
                  <div className="relative">
                    <Mail size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#839189]" />
                    <input id="mailbox-address" type="email" required autoComplete="username" value={mailboxAddress} onChange={(event) => setMailboxAddress(event.target.value)} className="min-h-12 w-full rounded-xl border border-[#d8e2dd] bg-white pl-11 pr-4 text-sm font-semibold text-[#20372d] outline-none transition placeholder:text-[#a4afa9] focus:border-[#2b715e] focus:ring-4 focus:ring-[#2b715e]/10" placeholder="you@company.co.ls" />
                  </div>
                </div>
                <div>
                  <label htmlFor="mailbox-password" className="mb-1.5 block text-[11px] font-extrabold text-[#31483f]">Mailbox password</label>
                  <div className="relative">
                    <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#839189]" />
                    <input id="mailbox-password" type={showPassword ? "text" : "password"} required autoComplete="current-password" value={mailboxPassword} onChange={(event) => setMailboxPassword(event.target.value)} className="min-h-12 w-full rounded-xl border border-[#d8e2dd] bg-white pl-11 pr-12 text-sm font-semibold text-[#20372d] outline-none transition placeholder:text-[#a4afa9] focus:border-[#2b715e] focus:ring-4 focus:ring-[#2b715e]/10" placeholder="Enter mailbox password" />
                    <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-[#75877f] transition hover:bg-[#edf4f1]" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 text-[10px] text-[#7b8a83]">
                  <span className="inline-flex items-center gap-1.5"><BadgeCheck size={13} className="text-[#34745f]" /> Secure mailbox session</span>
                  <span>Password changes are managed by your administrator.</span>
                </div>
                <button disabled={loading} className="group flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#14543f] px-4 text-sm font-extrabold text-white shadow-[0_14px_28px_rgba(20,84,63,.18)] transition hover:-translate-y-0.5 hover:bg-[#0f4635] disabled:cursor-wait disabled:translate-y-0 disabled:opacity-65">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Mail size={16} />}{loading ? "Signing in…" : "Open mailbox"}{!loading ? <ArrowRight size={15} className="transition group-hover:translate-x-0.5" /> : null}
                </button>
              </form>
            ) : (
              <form onSubmit={systemLogin} className="mt-6 space-y-4">
                <div>
                  <label htmlFor="system-email" className="mb-1.5 block text-[11px] font-extrabold text-[#31483f]">System account email</label>
                  <div className="relative">
                    <UserRound size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#839189]" />
                    <input id="system-email" type="email" required autoComplete="email" value={systemEmail} onChange={(event) => setSystemEmail(event.target.value)} readOnly={systemMfaRequired} className="min-h-12 w-full rounded-xl border border-[#d8e2dd] bg-white pl-11 pr-4 text-sm font-semibold text-[#20372d] outline-none transition read-only:bg-[#f4f7f5] focus:border-[#2b715e] focus:ring-4 focus:ring-[#2b715e]/10" placeholder="name@company.co.ls" />
                  </div>
                </div>
                <div>
                  <label htmlFor="system-password" className="mb-1.5 block text-[11px] font-extrabold text-[#31483f]">System password</label>
                  <div className="relative">
                    <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#839189]" />
                    <input id="system-password" type={showPassword ? "text" : "password"} required autoComplete="current-password" value={systemPassword} onChange={(event) => setSystemPassword(event.target.value)} readOnly={systemMfaRequired} className="min-h-12 w-full rounded-xl border border-[#d8e2dd] bg-white pl-11 pr-12 text-sm font-semibold text-[#20372d] outline-none transition read-only:bg-[#f4f7f5] focus:border-[#2b715e] focus:ring-4 focus:ring-[#2b715e]/10" placeholder="Enter system password" />
                    <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-[#75877f] transition hover:bg-[#edf4f1]" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
                  </div>
                </div>

                {systemMfaRequired ? (
                  <div className="rounded-2xl border border-[#e6d79b] bg-[#fffaf0] p-4">
                    <label htmlFor="system-mfa" className="mb-2 flex items-center gap-2 text-[11px] font-extrabold text-[#564b25]"><KeyRound size={15} /> Authenticator code</label>
                    <input id="system-mfa" value={systemMfaCode} onChange={(event) => setSystemMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus className="min-h-12 w-full rounded-xl border border-[#decf91] bg-white px-4 text-center text-xl font-black tracking-[.34em] text-[#263a31] outline-none focus:border-[#9d873d] focus:ring-4 focus:ring-[#c9ad4a]/15" placeholder="000000" />
                    <div className="mt-3 flex items-center gap-2 text-[10px] leading-4 text-[#786d4b]"><CheckCircle2 size={13} className="shrink-0" /> Your password was accepted. Complete MFA to continue.</div>
                  </div>
                ) : null}

                <div className="flex items-center justify-between gap-3 text-[10px]">
                  <span className="inline-flex items-center gap-1.5 text-[#7b8a83]"><ShieldCheck size={13} className="text-[#34745f]" /> Protected administration access</span>
                  <Link href="/forgot-password" className="font-extrabold text-[#286956] transition hover:text-[#123f32]">Forgot password?</Link>
                </div>

                <button disabled={loading} className="group flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#14543f] px-4 text-sm font-extrabold text-white shadow-[0_14px_28px_rgba(20,84,63,.18)] transition hover:-translate-y-0.5 hover:bg-[#0f4635] disabled:cursor-wait disabled:translate-y-0 disabled:opacity-65">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <LockKeyhole size={16} />}{loading ? "Signing in…" : systemMfaRequired ? "Verify and continue" : "Sign in to system"}{!loading ? <ArrowRight size={15} className="transition group-hover:translate-x-0.5" /> : null}
                </button>

                {systemMfaRequired ? <button type="button" onClick={() => { setSystemMfaRequired(false); setSystemMfaCode(""); setError(""); }} className="w-full text-center text-xs font-bold text-[#5e786e] transition hover:text-[#173f38]">Use a different system account</button> : null}
              </form>
            )}

            <div className="mt-7 rounded-2xl border border-[#d9e8e1] bg-[linear-gradient(135deg,#f2f9f6,#fbfdfc)] p-4">
              <div className="flex items-start gap-3">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#e3f2eb] text-[#1c6f56]"><ShieldCheck size={19} /></div>
                <div>
                  <p className="text-[11px] font-black text-[#29483e]">Secure access</p>
                  <p className="mt-1 text-[10px] leading-5 text-[#75877f]">Mailbox and system sessions use the platform’s existing protected authentication paths. Passwords are never displayed back to users.</p>
                </div>
              </div>
            </div>

            <div className="mt-6 border-t border-[#e4ebe7] pt-5 text-[10px] leading-5 text-[#84928c]">
              <p className="font-bold text-[#657970]">Need help?</p>
              <p className="mt-1">Contact your !THUTE platform administrator or use the system password recovery flow when available for your account.</p>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-bold text-[#557369]"><Link href="/docs" className="hover:text-[#164b3c]">Documentation</Link><Link href="/" className="hover:text-[#164b3c]">Platform home</Link></div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
