"use client";

import { FormEvent, KeyboardEvent, useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  Eye,
  EyeOff,
  Fingerprint,
  KeyRound,
  LockKeyhole,
  Mail,
  Network,
  ServerCog,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

const capabilities = [
  { label: "Identity", detail: "Tenant-aware access", icon: Fingerprint },
  { label: "DNS", detail: "Authoritative control", icon: Network },
  { label: "Mail", detail: "Secure operations", icon: Mail },
];

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  function detectCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState("CapsLock"));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    const form = new FormData(event.currentTarget);
    const mfaCode = String(form.get("mfa_code") || "").replace(/\s/g, "").trim();

    try {
      const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: String(form.get("email") || "").trim(),
          password: String(form.get("password") || ""),
          ...(mfaCode ? { mfa_code: mfaCode } : {}),
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = String(body.detail || "We could not sign you in with those credentials.");
        if (detail.toLowerCase().includes("mfa code required")) {
          setMfaRequired(true);
          setError("");
        } else if (detail.toLowerCase().includes("invalid mfa")) {
          setMfaRequired(true);
          setError("That authentication code was not accepted. Check your authenticator app and try again.");
        } else if (response.status === 401) {
          setError("The email address or password is incorrect.");
        } else {
          setError(detail);
        }
        return;
      }

      router.replace("/dashboard");
      router.refresh();
    } catch {
      setError("The secure control plane could not be reached. Please try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#071b2f] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_14%_18%,rgba(32,105,183,.36),transparent_30%),radial-gradient(circle_at_86%_20%,rgba(238,194,85,.13),transparent_26%),linear-gradient(135deg,#06172a_0%,#0b3266_52%,#071c34_100%)]" />
      <div className="absolute inset-0 opacity-[.17] [background-image:linear-gradient(rgba(255,255,255,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.08)_1px,transparent_1px)] [background-size:48px_48px]" />
      <div className="absolute -left-28 bottom-[-9rem] h-[30rem] w-[30rem] rounded-full border border-white/10 bg-cyan-400/10 blur-3xl" />
      <div className="absolute right-[8%] top-[8%] h-52 w-52 rounded-full bg-amber-300/10 blur-3xl" />

      <div className="relative mx-auto grid min-h-screen w-full max-w-[1320px] items-center gap-12 px-5 py-8 lg:grid-cols-[1.08fr_.92fr] lg:px-10 xl:gap-20">
        <section className="hidden lg:block">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[.07] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[.15em] text-slate-200 backdrop-blur-xl">
            <Sparkles size={14} className="text-amber-300" />
            Mailbox DNS secure control plane
          </div>

          <h1 className="mt-7 max-w-[680px] text-[56px] font-black leading-[.98] tracking-[-.055em] text-white xl:text-[66px]">
            One secure place for your email and DNS infrastructure.
          </h1>
          <p className="mt-6 max-w-[620px] text-[16px] leading-8 text-slate-300/85">
            Control organisations, domains, authoritative DNS and mail services through a hardened multi-tenant platform built for serious business operations.
          </p>

          <div className="mt-9 grid max-w-[650px] grid-cols-3 gap-3">
            {capabilities.map(({ label, detail, icon: Icon }) => (
              <div key={label} className="group rounded-2xl border border-white/10 bg-white/[.065] p-4 backdrop-blur-xl transition hover:-translate-y-1 hover:border-white/20 hover:bg-white/[.09]">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-amber-300"><Icon size={18} /></div>
                <p className="mt-4 text-sm font-extrabold text-white">{label}</p>
                <p className="mt-1 text-[11px] leading-5 text-slate-400">{detail}</p>
              </div>
            ))}
          </div>

          <div className="mt-8 flex max-w-[650px] items-center gap-3 rounded-2xl border border-emerald-300/15 bg-emerald-300/[.06] px-4 py-3 text-xs text-emerald-50/85 backdrop-blur-xl">
            <ShieldCheck size={18} className="shrink-0 text-emerald-300" />
            <span>HttpOnly sessions, rotating refresh tokens, MFA and auditable security events are built into the control plane.</span>
          </div>
        </section>

        <section className="mx-auto w-full max-w-[500px]">
          <div className="rounded-[32px] border border-white/20 bg-white/[.98] p-5 text-[#173228] shadow-[0_40px_120px_rgba(0,0,0,.42)] backdrop-blur-2xl sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#123a38] text-sm font-black text-[#f1de8b] shadow-[0_10px_28px_rgba(18,58,56,.22)]">MD</div>
                <div>
                  <p className="text-sm font-black tracking-[-.01em] text-[#173228]">Mailbox DNS</p>
                  <p className="mt-0.5 text-[9px] font-extrabold uppercase tracking-[.16em] text-[#849189]">Protected platform access</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-[.11em] text-emerald-700">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Secure
              </div>
            </div>

            <div className="mt-8">
              <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[.14em] text-[#55766c]">
                <ServerCog size={14} /> Administration
              </div>
              <h2 className="mt-3 text-[34px] font-black tracking-[-.045em] text-[#173228]">{mfaRequired ? "Verify it’s you" : "Welcome back"}</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-[#6f8178]">
                {mfaRequired
                  ? "Your password is correct. Enter the current 6-digit code from your authenticator app to finish signing in."
                  : "Sign in to manage your organisation, domains, DNS and mail infrastructure."}
              </p>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-2">
              <div className={`rounded-xl border px-3 py-2.5 ${mfaRequired ? "border-emerald-200 bg-emerald-50" : "border-[#dce5e0] bg-[#f8faf9]"}`}>
                <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[.08em] text-[#678078]">
                  {mfaRequired ? <CheckCircle2 size={14} className="text-emerald-600" /> : <LockKeyhole size={14} />} Password
                </div>
              </div>
              <div className={`rounded-xl border px-3 py-2.5 ${mfaRequired ? "border-[#d6c278] bg-[#fffaf0]" : "border-[#dce5e0] bg-[#f8faf9]"}`}>
                <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[.08em] text-[#678078]"><KeyRound size={14} /> MFA when enabled</div>
              </div>
            </div>

            {!mfaRequired ? (
              <div className="mt-6">
                <a
                  href={`${API}/auth/ithute/login`}
                  className="group flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-[#b7d1c8] bg-[#eff8f4] px-4 text-sm font-extrabold text-[#174a40] shadow-sm transition hover:-translate-y-0.5 hover:border-[#7fb0a0] hover:bg-[#e7f4ef]"
                >
                  <Fingerprint size={18} />
                  Sign in with Ithute
                  <ArrowRight size={16} className="transition group-hover:translate-x-0.5" />
                </a>
                <div className="my-5 flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[.12em] text-[#98a49e]">
                  <span className="h-px flex-1 bg-[#e1e7e3]" />
                  <span>or use a local account</span>
                  <span className="h-px flex-1 bg-[#e1e7e3]" />
                </div>
              </div>
            ) : null}

            <form className={mfaRequired ? "mt-6 space-y-4" : "space-y-4"} onSubmit={submit}>
              <div>
                <label className="mb-1.5 block text-[11px] font-extrabold text-[#243b31]" htmlFor="email">Email address</label>
                <div className="relative">
                  <Mail size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#829087]" />
                  <input id="email" className="min-h-12 w-full rounded-xl border border-[#d9e2dd] bg-white pl-11 pr-4 text-sm font-semibold text-[#20372d] outline-none transition placeholder:text-[#a7b1ab] focus:border-[#2d6d66] focus:ring-4 focus:ring-[#2d6d66]/10" name="email" type="email" autoComplete="email" required placeholder="name@company.co.ls" disabled={mfaRequired} />
                </div>
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <label className="block text-[11px] font-extrabold text-[#243b31]" htmlFor="password">Password</label>
                  {capsLock ? <span className="text-[10px] font-bold text-amber-700">Caps Lock is on</span> : null}
                </div>
                <div className="relative">
                  <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#829087]" />
                  <input id="password" className="min-h-12 w-full rounded-xl border border-[#d9e2dd] bg-white pl-11 pr-12 text-sm font-semibold text-[#20372d] outline-none transition placeholder:text-[#a7b1ab] focus:border-[#2d6d66] focus:ring-4 focus:ring-[#2d6d66]/10" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required placeholder="Enter your password" onKeyDown={detectCapsLock} onKeyUp={detectCapsLock} disabled={mfaRequired} />
                  <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-[#708078] transition hover:bg-[#eef4f1] hover:text-[#264d46]" aria-label={showPassword ? "Hide password" : "Show password"}>
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>

              {mfaRequired ? (
                <div className="rounded-2xl border border-[#eadb9f] bg-[#fffaf0] p-4">
                  <label className="mb-2 block text-[11px] font-extrabold text-[#4a4227]" htmlFor="mfa_code">Authenticator code</label>
                  <div className="relative">
                    <KeyRound size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#8e7935]" />
                    <input id="mfa_code" className="min-h-13 w-full rounded-xl border border-[#e3d394] bg-white pl-11 pr-4 text-center text-xl font-black tracking-[.35em] text-[#263a31] outline-none transition placeholder:tracking-[.25em] placeholder:text-[#c3b77f] focus:border-[#9d873d] focus:ring-4 focus:ring-[#c9ad4a]/15" name="mfa_code" inputMode="numeric" pattern="[0-9]*" autoComplete="one-time-code" maxLength={6} required placeholder="000000" autoFocus />
                  </div>
                  <p className="mt-2 text-[10px] leading-4 text-[#7b704d]">Codes rotate approximately every 30 seconds. Never share a code with anyone.</p>
                </div>
              ) : null}

              {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold leading-5 text-red-700">{error}</div> : null}

              <button className="group flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#123a38] px-4 text-sm font-extrabold text-white shadow-[0_14px_30px_rgba(18,58,56,.20)] transition hover:-translate-y-0.5 hover:bg-[#285b55] disabled:cursor-wait disabled:translate-y-0 disabled:opacity-70" type="submit" disabled={loading}>
                {loading ? "Securing your session…" : mfaRequired ? "Verify and continue" : "Sign in securely"}
                {!loading ? <ArrowRight size={16} className="transition group-hover:translate-x-0.5" /> : null}
              </button>

              {mfaRequired ? <button type="button" onClick={() => { setMfaRequired(false); setError(""); }} className="w-full text-center text-xs font-bold text-[#55766c] transition hover:text-[#173f38]">Use a different account</button> : null}
            </form>

            <div className="mt-6 border-t border-[#e5eae7] pt-5">
              <div className="flex items-center justify-center gap-2 text-[10px] font-semibold text-[#87938d]"><BadgeCheck size={13} className="text-[#4f7d72]" /> HttpOnly cookies · rotating sessions · MFA capable</div>
              <div className="mt-3 flex items-center justify-center gap-4 text-[10px] font-bold text-[#6c7c74]">
                <Link href="/docs" className="transition hover:text-[#173f38]">Security & setup docs</Link>
                <span className="h-1 w-1 rounded-full bg-[#c0cac5]" />
                <Link href="/" className="transition hover:text-[#173f38]">Back to website</Link>
              </div>
            </div>
          </div>

          <p className="mx-auto mt-5 max-w-md text-center text-[10px] leading-5 text-slate-400">
            Access is monitored and security-sensitive actions may be recorded in the platform audit log.
          </p>
        </section>
      </div>
    </main>
  );
}
