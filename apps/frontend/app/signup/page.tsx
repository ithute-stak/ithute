"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Building2,
  Globe2,
  KeyRound,
  LockKeyhole,
  Mail,
  Server,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type PlatformMode = {
  mode: string;
  security_level: string;
  signup_enabled: boolean;
  setup_required: boolean;
  panel_url?: string;
};

type PricingPlan = {
  code: string;
  name: string;
  currency: string;
  monthly_price_minor: number;
  annual_price_minor?: number | null;
  setup_fee_minor?: number;
  included_mailboxes: number;
  included_domains: number;
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_database_limit: number;
  featured?: boolean;
};

function money(minor?: number | null) {
  if (minor == null) return "Custom pricing";
  return `M${(minor / 100).toLocaleString("en-LS", { maximumFractionDigits: 2 })}`;
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className={`${compact ? "h-10 w-10 text-xl" : "h-12 w-12 text-2xl"} grid place-items-center rounded-2xl bg-[#d8c56a] font-black text-[#123a38] shadow-lg shadow-black/10`}>!</span>
      <span>
        <span className={`${compact ? "text-base" : "text-lg"} block font-black tracking-[-.04em]`}>thute</span>
        <span className="block text-[8px] font-black uppercase tracking-[.19em] opacity-50">Digital solutions</span>
      </span>
    </div>
  );
}

export default function SignupPage() {
  const [plan, setPlan] = useState("");
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{ company: string; email: string } | null>(null);
  const [platform, setPlatform] = useState<PlatformMode | null>(null);

  useEffect(() => {
    const requestedPlan = new URLSearchParams(window.location.search).get("plan");
    void Promise.all([
      fetch(`${API}/public/platform-mode`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(`${API}/public/pricing`, { credentials: "include", cache: "no-store" })
        .then(async (r) => {
          if (!r.ok) throw new Error("Unable to load packages");
          return r.json();
        })
        .catch(() => ({ items: [] })),
    ]).then(([mode, pricing]) => {
      setPlatform(mode);
      const available = Array.isArray(pricing?.items) ? pricing.items as PricingPlan[] : [];
      setPlans(available);
      const requestedExists = requestedPlan && available.some((item) => item.code === requestedPlan);
      setPlan(requestedExists ? requestedPlan : (available.find((item) => item.featured)?.code || available[0]?.code || ""));
      setPlansLoading(false);
    });
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!plan) {
      setError("No customer package is currently available. Please contact Ithute support.");
      return;
    }
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    const body = {
      company_name: String(data.get("company_name") || "").trim(),
      full_name: String(data.get("full_name") || "").trim(),
      email: String(data.get("email") || "").trim(),
      phone: String(data.get("phone") || "").trim() || null,
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
        setError(typeof payload.detail === "string" ? payload.detail : "We could not create this Ithute account yet.");
        return;
      }
      await fetch(`${API}/public/email-verification/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: body.email }),
      });
      setCreated({ company: payload.tenant.name, email: payload.user.email });
    } catch {
      setError("The secure Ithute control plane could not be reached. Please try again shortly.");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#edf3ef] px-5 py-10 text-[#20342a]">
        <div className="absolute -left-32 top-10 h-96 w-96 rounded-full bg-[#d8c56a]/15 blur-3xl" />
        <div className="absolute -right-32 bottom-0 h-96 w-96 rounded-full bg-[#285b55]/10 blur-3xl" />
        <div className="relative w-full max-w-xl rounded-[32px] border border-[#d9e3dd] bg-white p-7 text-center shadow-[0_28px_80px_rgba(18,58,56,.13)] sm:p-10">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-[#123a38] text-[#d8c56a] shadow-lg shadow-[#123a38]/15"><BadgeCheck size={31} /></div>
          <p className="mt-6 text-[10px] font-black uppercase tracking-[.16em] text-[#6e7f77]">Registration received</p>
          <h1 className="mt-3 text-3xl font-black tracking-[-.045em]">Check your email to continue.</h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-7 text-[#718078]">
            We created the registration for <b className="text-[#29483d]">{created.company}</b> and sent a verification link to <b className="text-[#29483d]">{created.email}</b>. Verify the address before signing in to production services.
          </p>
          <div className="mt-6 rounded-2xl border border-[#e5e9df] bg-[#fffdf4] p-4 text-left text-xs leading-6 text-[#6b6244]">
            <div className="flex gap-3"><ShieldCheck className="mt-0.5 shrink-0 text-[#8a7632]" size={18} /><span>Your password is never sent by email. Use only the verification link sent by Ithute, then return to the secure sign-in page. Your selected package starts only after Ithute approves the company application.</span></div>
          </div>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link href="/login" className="inline-flex items-center gap-2 rounded-xl bg-[#123a38] px-6 py-3 text-sm font-black text-white shadow-lg shadow-[#123a38]/10">Continue to sign in <ArrowRight size={15} /></Link>
            <Link href="/" className="inline-flex items-center gap-2 rounded-xl border border-[#dce4df] px-5 py-3 text-sm font-black text-[#456057]"><ArrowLeft size={15} /> Home</Link>
          </div>
        </div>
      </main>
    );
  }

  if (platform && !platform.signup_enabled) {
    return (
      <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#edf3ef] px-5 py-10 text-[#20342a]">
        <div className="absolute inset-x-0 top-0 h-56 bg-gradient-to-b from-[#123a38] to-transparent opacity-[.06]" />
        <div className="relative grid w-full max-w-4xl overflow-hidden rounded-[30px] border border-[#d9e3dd] bg-white shadow-[0_30px_90px_rgba(18,58,56,.14)] md:grid-cols-[.8fr_1.2fr]">
          <section className="bg-[#123a38] p-7 text-white sm:p-9">
            <BrandMark />
            <p className="mt-12 text-[10px] font-black uppercase tracking-[.17em] text-[#d8c56a]">Protected onboarding</p>
            <h1 className="mt-3 text-3xl font-black tracking-[-.045em]">Customer registration is temporarily protected.</h1>
            <p className="mt-4 text-sm leading-7 text-white/60">This screen appears only while Ithute is deliberately in bootstrap or platform-domain setup mode.</p>
          </section>
          <section className="p-7 sm:p-9">
            <div className="inline-flex items-center gap-2 rounded-full border border-[#dce9e3] bg-[#f3f8f5] px-3 py-2 text-[9px] font-black uppercase tracking-[.12em] text-[#367062]"><ShieldCheck size={14} /> Secure bootstrap mode</div>
            <h2 className="mt-6 text-3xl font-black tracking-[-.04em]">Public signup is not open on this platform state.</h2>
            <p className="mt-4 text-sm leading-7 text-[#718078]">The platform owner must complete the authoritative-domain and secure-email setup before customer registration can accept applications.</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-[#e2e8e4] bg-[#f8faf9] p-4"><Globe2 size={18} className="text-[#285b55]" /><p className="mt-3 text-xs font-black">Verified platform domain</p><p className="mt-1 text-[10px] leading-5 text-[#718078]">Registration never opens from a raw bootstrap address.</p></div>
              <div className="rounded-2xl border border-[#e2e8e4] bg-[#f8faf9] p-4"><Mail size={18} className="text-[#285b55]" /><p className="mt-3 text-xs font-black">Secure email delivery</p><p className="mt-1 text-[10px] leading-5 text-[#718078]">Verification mail must be available before public signup opens.</p></div>
            </div>
            <div className="mt-7 flex flex-wrap gap-3"><Link href="/login" className="inline-flex items-center gap-2 rounded-xl bg-[#123a38] px-5 py-3 text-sm font-black text-white">Platform owner sign in <ArrowRight size={15} /></Link><Link href="/" className="inline-flex items-center gap-2 rounded-xl border border-[#dce4df] px-5 py-3 text-sm font-black text-[#456057]"><ArrowLeft size={15} /> Back home</Link></div>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#eef3f0] text-[#20342a]">
      <header className="border-b border-[#dbe4df] bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1220px] items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <Link href="/" className="text-[#123a38]"><BrandMark compact /></Link>
          <div className="flex items-center gap-2"><Link href="/pricing" className="hidden rounded-lg px-3 py-2 text-xs font-black text-[#537068] sm:inline">View packages</Link><Link href="/login" className="rounded-xl border border-[#d5e1db] px-4 py-2.5 text-xs font-black text-[#123a38]">Sign in</Link></div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1220px] gap-7 px-5 py-8 sm:px-8 lg:grid-cols-[.86fr_1.14fr] lg:items-stretch lg:py-12">
        <section className="relative overflow-hidden rounded-[30px] bg-[#123a38] p-7 text-white shadow-[0_24px_70px_rgba(18,58,56,.18)] sm:p-9 lg:p-10">
          <div className="absolute -right-28 -top-28 h-72 w-72 rounded-full bg-[#d8c56a]/10 blur-2xl" />
          <div className="absolute -bottom-24 -left-20 h-64 w-64 rounded-full bg-emerald-300/10 blur-2xl" />
          <div className="relative">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[9px] font-black uppercase tracking-[.14em] text-[#d8c56a]"><Sparkles size={13} /> Start with Ithute</div>
            <h1 className="mt-6 max-w-md text-4xl font-black leading-[1.03] tracking-[-.055em] sm:text-5xl">Your company. One secure digital workspace.</h1>
            <p className="mt-5 max-w-md text-sm leading-7 text-white/62">Create your organisation, verify your work email and bring hosting, websites, DNS and professional email into one Ithute account.</p>

            <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {[
                [Server, "Managed hosting", "Application hosting with enforced limits and secure deployment."],
                [Mail, "Business email", "Professional mailboxes under your own domains."],
                [Globe2, "Domains & DNS", "Authoritative DNS and domain operations from one place."],
                [ShieldCheck, "Secure access", "Email verification, protected sessions and MFA support."],
              ].map(([Icon, title, copy]) => {
                const IconComponent = Icon as typeof Server;
                return <div key={String(title)} className="rounded-2xl border border-white/10 bg-white/[.055] p-4"><IconComponent size={17} className="text-[#d8c56a]" /><p className="mt-3 text-xs font-black">{String(title)}</p><p className="mt-1 text-[10px] leading-5 text-white/50">{String(copy)}</p></div>;
              })}
            </div>

            <div className="mt-8 border-t border-white/10 pt-6 text-[10px] leading-5 text-white/48">By creating an account, your organisation remains isolated from other Ithute customers. Platform permissions and resource limits are enforced server-side.</div>
          </div>
        </section>

        <section className="rounded-[30px] border border-[#dbe4df] bg-white p-6 shadow-sm sm:p-8 lg:p-9">
          <div className="flex flex-col gap-4 border-b border-[#e8eeea] pb-6 sm:flex-row sm:items-start sm:justify-between">
            <div><p className="text-[10px] font-black uppercase tracking-[.15em] text-[#718078]">Company registration</p><h2 className="mt-2 text-3xl font-black tracking-[-.045em]">Create your Ithute account</h2><p className="mt-2 text-xs leading-5 text-[#718078]">Use company details you can verify. You can add more team members later.</p></div>
            <span className="inline-flex shrink-0 items-center gap-2 self-start rounded-full border border-emerald-100 bg-emerald-50 px-3 py-2 text-[9px] font-black uppercase tracking-[.1em] text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Secure signup</span>
          </div>

          <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
            <label className="sm:col-span-2"><span className="flex items-center gap-2 text-xs font-black"><Building2 size={14} className="text-[#56746b]" /> Company name</span><input name="company_name" required minLength={2} autoComplete="organization" className="input mt-2" placeholder="Example (Pty) Ltd" /></label>
            <label><span className="flex items-center gap-2 text-xs font-black"><UserRound size={14} className="text-[#56746b]" /> Your full name</span><input name="full_name" required autoComplete="name" className="input mt-2" placeholder="Account owner" /></label>
            <label><span className="text-xs font-black">Phone number</span><input name="phone" autoComplete="tel" className="input mt-2" placeholder="+266 ..." /></label>
            <label className="sm:col-span-2"><span className="flex items-center gap-2 text-xs font-black"><Mail size={14} className="text-[#56746b]" /> Work email</span><input type="email" name="email" required autoComplete="email" className="input mt-2" placeholder="you@company.co.ls" /></label>
            <label className="sm:col-span-2"><span className="flex items-center gap-2 text-xs font-black"><KeyRound size={14} className="text-[#56746b]" /> Password</span><input type="password" name="password" required minLength={12} autoComplete="new-password" className="input mt-2" placeholder="At least 12 characters" /><span className="mt-1 block text-[9px] leading-4 text-[#819087]">Use a unique password. You can enable multi-factor authentication after sign-in.</span></label>
            <label className="sm:col-span-2">
              <span className="text-xs font-black">Package</span>
              <select value={plan} onChange={(e) => setPlan(e.target.value)} disabled={plansLoading || plans.length === 0} className="input mt-2">
                {plansLoading ? <option value="">Loading current packages…</option> : null}
                {!plansLoading && plans.length === 0 ? <option value="">No package currently available</option> : null}
                {plans.map((item) => (
                  <option value={item.code} key={item.code}>
                    {item.name} — {item.annual_price_minor != null ? `${money(item.annual_price_minor)}/yr` : `${money(item.monthly_price_minor)}/mo`}
                  </option>
                ))}
              </select>
              {plans.find((item) => item.code === plan) ? (
                <p className="mt-2 text-[9px] leading-4 text-[#718078]">
                  {Math.round((plans.find((item) => item.code === plan)?.hosting_storage_mb || 0) / 1024)} GB app storage · {plans.find((item) => item.code === plan)?.included_mailboxes} mailboxes · {plans.find((item) => item.code === plan)?.included_hosted_projects} website/app{plans.find((item) => item.code === plan)?.included_hosted_projects === 1 ? "" : "s"} · {plans.find((item) => item.code === plan)?.hosting_database_limit} managed databases.
                </p>
              ) : <p className="mt-1 text-[9px] leading-4 text-[#718078]">Package availability is controlled by the Ithute owner catalogue.</p>}
            </label>

            <div className="sm:col-span-2 rounded-2xl border border-[#e2e9e5] bg-[#f8faf9] p-4">
              <label className="flex items-start gap-3 text-xs leading-5 text-[#617168]"><input type="checkbox" name="terms" required className="mt-1 h-4 w-4 accent-[#123a38]" /><span>I accept the <Link className="font-black text-[#285b55]" href="/legal#terms">Terms of Service</Link> and <Link className="font-black text-[#285b55]" href="/legal#acceptable-use">Acceptable Use Policy</Link>.</span></label>
            </div>

            {error ? <div role="alert" className="sm:col-span-2 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-xs font-bold leading-5 text-red-700"><LockKeyhole size={16} className="mt-0.5 shrink-0" />{error}</div> : null}
            <button disabled={busy || plansLoading || !plan} className="sm:col-span-2 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#123a38] px-5 text-sm font-black text-white shadow-[0_14px_30px_rgba(18,58,56,.16)] transition hover:-translate-y-0.5 hover:bg-[#285b55] disabled:cursor-wait disabled:translate-y-0 disabled:opacity-60">{busy ? "Creating your secure workspace…" : "Submit company application"}{!busy ? <ArrowRight size={16} /> : null}</button>
          </form>

          <div className="mt-6 flex flex-col gap-3 border-t border-[#e8eeea] pt-5 text-xs text-[#718078] sm:flex-row sm:items-center sm:justify-between"><span>Already registered? <Link href="/login" className="font-black text-[#285b55]">Sign in securely</Link></span><Link href="/pricing" className="inline-flex items-center gap-1 font-black text-[#45655b]">Compare packages <ArrowRight size={13} /></Link></div>
        </section>
      </div>
    </main>
  );
}
