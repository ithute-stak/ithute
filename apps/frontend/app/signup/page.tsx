"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type PlatformMode = {
  mode: string;
  security_level: string;
  signup_enabled: boolean;
  setup_required: boolean;
  panel_url?: string;
};

export default function SignupPage() {
  const [plan, setPlan] = useState("business");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{ company: string; email: string } | null>(null);
  const [platform, setPlatform] = useState<PlatformMode | null>(null);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("plan");
    if (p) setPlan(p);
    void fetch(`${API}/public/platform-mode`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setPlatform)
      .catch(() => setPlatform(null));
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    const body = {
      company_name: String(data.get("company_name") || ""),
      full_name: String(data.get("full_name") || ""),
      email: String(data.get("email") || ""),
      phone: String(data.get("phone") || "") || null,
      password: String(data.get("password") || ""),
      plan_code: plan,
      terms_accepted: Boolean(data.get("terms")),
    };
    try {
      const r = await fetch(`${API}/public/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(typeof payload.detail === "string" ? payload.detail : "Unable to create account");
        return;
      }
      await fetch(`${API}/public/email-verification/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: body.email }),
      });
      setCreated({ company: payload.tenant.name, email: payload.user.email });
    } catch {
      setError("Unable to reach the Mailbox DNS control plane");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f4f6f4] px-5">
        <div className="w-full max-w-lg rounded-3xl border border-[#dfe6e2] bg-white p-8 text-center shadow-sm">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#123a38] text-xl font-black text-[#d8c56a]">✓</div>
          <h1 className="mt-5 text-2xl font-black">Your company account is ready.</h1>
          <p className="mt-3 text-sm leading-6 text-[#718078]">
            {created.company} has a 14-day trial. We sent an email-verification link to <b>{created.email}</b>. Verify it before production sign-in.
          </p>
          <Link href="/login" className="mt-6 inline-flex rounded-xl bg-[#123a38] px-6 py-3 text-sm font-black text-white">Continue to sign in</Link>
        </div>
      </main>
    );
  }

  if (platform && !platform.signup_enabled) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f4f6f4] px-5">
        <div className="w-full max-w-xl rounded-3xl border border-[#dfe6e2] bg-white p-8 shadow-sm">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#123a38] font-black text-[#d8c56a]">MD</div>
          <p className="mt-7 text-xs font-black uppercase tracking-[.15em] text-[#806800]">Secure bootstrap mode</p>
          <h1 className="mt-3 text-3xl font-black tracking-[-.04em] text-[#21342a]">Customer signup is not public yet.</h1>
          <p className="mt-4 text-sm leading-7 text-[#718078]">
            Mailbox DNS is running on its bootstrap server address. The platform owner must configure and verify the platform&apos;s own authoritative domain before public customer registration opens.
          </p>
          <div className="mt-6 rounded-2xl bg-[#f8faf8] p-4 text-xs leading-6 text-[#53655d]">
            No external CAPTCHA provider is used. After domain activation, signup remains protected by fail-closed Redis rate limits, email verification, secure HTTPS sessions and platform security controls.
          </div>
          <Link href="/login" className="mt-6 inline-flex rounded-xl bg-[#123a38] px-6 py-3 text-sm font-black text-white">Platform owner sign in</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f4f6f4]">
      <div className="mx-auto grid min-h-screen max-w-[1180px] items-center gap-10 px-5 py-10 lg:grid-cols-[.85fr_1.15fr]">
        <section className="rounded-3xl bg-[#123a38] p-8 text-white lg:p-10">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#d8c56a] font-black text-[#123a38]">MD</div>
          <p className="mt-8 text-xs font-black uppercase tracking-[.15em] text-[#d8c56a]">Start your hosting account</p>
          <h1 className="mt-3 text-4xl font-black tracking-[-.04em]">Business email and DNS under your control.</h1>
          <p className="mt-5 text-sm leading-7 text-white/65">Create the company, verify your email, start a trial and provision business mail without waiting for a platform administrator.</p>
          <div className="mt-7 space-y-3 text-sm text-white/80">
            <p>✓ 14-day trial</p><p>✓ Email-verified account security</p><p>✓ Fail-closed signup rate limiting</p><p>✓ Mail + DNS + Webmail + monitoring</p>
          </div>
        </section>
        <section className="rounded-3xl border border-[#dfe6e2] bg-white p-6 shadow-sm sm:p-8">
          <div className="flex items-center justify-between"><div><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Customer signup</p><h2 className="mt-2 text-2xl font-black">Create your company</h2></div><Link href="/pricing" className="text-xs font-black text-[#285b55]">Pricing</Link></div>
          <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
            <label className="sm:col-span-2"><span className="text-xs font-bold">Company name</span><input name="company_name" required minLength={2} className="input mt-1" placeholder="Example (Pty) Ltd" /></label>
            <label><span className="text-xs font-bold">Your full name</span><input name="full_name" required className="input mt-1" /></label>
            <label><span className="text-xs font-bold">Phone</span><input name="phone" className="input mt-1" placeholder="+266 ..." /></label>
            <label className="sm:col-span-2"><span className="text-xs font-bold">Work email</span><input type="email" name="email" required className="input mt-1" /></label>
            <label className="sm:col-span-2"><span className="text-xs font-bold">Password</span><input type="password" name="password" required minLength={12} className="input mt-1" /></label>
            <label className="sm:col-span-2"><span className="text-xs font-bold">Plan</span><select value={plan} onChange={(e) => setPlan(e.target.value)} className="input mt-1"><option value="starter">Starter</option><option value="business">Business</option><option value="enterprise">Enterprise</option></select></label>
            <label className="sm:col-span-2 flex items-start gap-2 text-xs leading-5 text-[#617168]"><input type="checkbox" name="terms" required className="mt-1" /><span>I accept the <Link className="font-bold text-[#285b55]" href="/legal#terms">Terms of Service</Link> and <Link className="font-bold text-[#285b55]" href="/legal#acceptable-use">Acceptable Use Policy</Link>.</span></label>
            {error ? <p className="sm:col-span-2 rounded-lg bg-red-50 p-3 text-xs font-bold text-red-700">{error}</p> : null}
            <button disabled={busy} className="btn-primary sm:col-span-2">{busy ? "Creating account…" : "Start 14-day trial"}</button>
          </form>
          <p className="mt-5 text-center text-xs text-[#718078]">Already have an account? <Link href="/login" className="font-black text-[#285b55]">Sign in</Link></p>
        </section>
      </div>
    </main>
  );
}
