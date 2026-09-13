"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Building2, Check, CreditCard, Globe2, LogIn, Mail, Server, ShieldCheck } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Plan = {
  code: string;
  name: string;
  monthly_price_minor: number;
  price_from: boolean;
  description: string;
  included_hosted_projects: number;
  included_domains: number;
  included_mailboxes: number;
  website_pages: number;
  includes_website_design: boolean;
  includes_logo_design: boolean;
  includes_brand_guide: boolean;
  includes_business_templates: boolean;
  support_level: string;
  minimum_term_months: number;
};

export default function ChoosePackagePage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planCode, setPlanCode] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setPlanCode(new URLSearchParams(window.location.search).get("plan") || "");
    void fetch(`${API}/public/hosting-pricing`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((body) => setPlans(body.items || []))
      .finally(() => setLoading(false));
  }, []);

  const plan = useMemo(() => plans.find((item) => item.code === planCode) || plans[0], [plans, planCode]);
  const benefits = useMemo(() => {
    if (!plan) return [];
    const items = [
      plan.includes_website_design ? `Responsive website${plan.website_pages ? ` — up to ${plan.website_pages} pages` : ""}` : null,
      plan.includes_logo_design ? "Logo / brand setup" : null,
      plan.includes_brand_guide ? "Brand identity guide" : null,
      plan.includes_business_templates ? "Business document templates" : null,
      `${plan.included_hosted_projects} hosted project${plan.included_hosted_projects === 1 ? "" : "s"}`,
      `${plan.included_mailboxes} professional mailbox${plan.included_mailboxes === 1 ? "" : "es"}`,
      `${plan.included_domains} domain${plan.included_domains === 1 ? "" : "s"}`,
      `${plan.support_level} support`,
    ];
    return items.filter(Boolean) as string[];
  }, [plan]);

  return (
    <main className="min-h-screen bg-[#f4f6f4] text-[#21342a]">
      <header className="border-b border-[#dfe6e2] bg-[#123a38] text-white">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <Link href="/" className="flex items-center gap-3 font-black"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[#123a38]">!I</span>Ithute Solutions</Link>
          <Link href="/pricing" className="inline-flex items-center gap-2 text-xs font-black text-white/75 hover:text-white"><ArrowLeft size={14}/>All packages</Link>
        </div>
      </header>

      <section className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 lg:py-16">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Choose how to continue</p>
          <h1 className="mt-3 text-3xl font-black tracking-[-.04em] sm:text-4xl">Your package, your organisation workspace.</h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-[#718078]">Existing customers sign in as an organisation owner. New customers create an organisation account with the selected package, then manage billing, usage, domains, email and hosting from one workspace.</p>
        </div>

        {loading ? <div className="mt-10 text-center text-sm text-[#718078]">Loading selected package…</div> : plan ? (
          <div className="mt-10 grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
            <article className="rounded-3xl bg-[#123a38] p-6 text-white shadow-sm sm:p-7">
              <p className="text-[10px] font-black uppercase tracking-[.13em] text-[#d8c56a]">Selected package</p>
              <h2 className="mt-3 text-2xl font-black">{plan.name}</h2>
              <p className="mt-2 text-3xl font-black">{plan.price_from ? "From " : ""}M {(plan.monthly_price_minor / 100).toLocaleString()}<span className="text-xs font-bold text-white/55"> / month</span></p>
              <p className="mt-4 text-xs leading-6 text-white/65">{plan.description}</p>
              {plan.minimum_term_months > 1 ? <p className="mt-3 rounded-xl border border-[#d8c56a]/25 bg-[#d8c56a]/10 px-3 py-2 text-[10px] font-bold text-[#f6e9a8]">Creative build included on a {plan.minimum_term_months}-month agreement.</p> : null}
              <ul className="mt-6 space-y-2.5 text-xs text-white/80">{benefits.map((benefit) => <li key={benefit} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-[#d8c56a]"/><span>{benefit}</span></li>)}</ul>
            </article>

            <div className="grid gap-4">
              <article className="rounded-3xl border border-[#dfe6e2] bg-white p-6 shadow-sm sm:p-7">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#edf4f1] text-[#285b55]"><LogIn size={19}/></div>
                <p className="mt-4 text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Already an Ithute customer?</p>
                <h2 className="mt-2 text-xl font-black">Sign in as organisation owner</h2>
                <p className="mt-2 text-xs leading-6 text-[#718078]">Open your existing organisation workspace to view its current package, invoices, usage and services. Your existing subscription is not changed just by viewing this public package.</p>
                <Link href="/login" className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#123a38] px-4 py-3 text-sm font-black text-white">Sign in to organisation <ArrowRight size={15}/></Link>
              </article>

              <article className="rounded-3xl border border-[#d8c56a] bg-[#fffdf4] p-6 shadow-sm sm:p-7">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#f4e8a8] text-[#5d521f]"><Building2 size={19}/></div>
                <p className="mt-4 text-[10px] font-black uppercase tracking-[.12em] text-[#806f2c]">New customer</p>
                <h2 className="mt-2 text-xl font-black">Create an organisation account</h2>
                <p className="mt-2 text-xs leading-6 text-[#6f775f]">Create your company workspace with <b>{plan.name}</b> already selected. After email verification and sign-in, the organisation owner can manage the account from the client portal.</p>
                <Link href={`/signup?plan=${encodeURIComponent(plan.code)}`} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#d8c56a] px-4 py-3 text-sm font-black text-[#123a38]">Create organisation <ArrowRight size={15}/></Link>
              </article>
            </div>
          </div>
        ) : <div className="mt-10 rounded-2xl border border-red-200 bg-red-50 p-5 text-center text-sm font-bold text-red-700">That package is not currently available. <Link href="/pricing" className="underline">Return to packages</Link>.</div>}

        <section className="mt-8 rounded-3xl border border-[#dfe6e2] bg-white p-6 sm:p-7">
          <p className="text-[10px] font-black uppercase tracking-[.13em] text-[#718078]">Organisation self-service workspace</p>
          <h2 className="mt-2 text-xl font-black">Everything the customer needs after sign-in.</h2>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[{icon:CreditCard,title:"Billing & package",copy:"Current subscription, invoices and usage."},{icon:Globe2,title:"Domains & DNS",copy:"Domains, verification, DNS zones and security."},{icon:Mail,title:"Professional email",copy:"Mailboxes, webmail and transactional email."},{icon:Server,title:"Application hosting",copy:"Hosted projects, resources and deployments."},{icon:Building2,title:"Organisation",copy:"Company context, memberships and settings."},{icon:ShieldCheck,title:"Security & support",copy:"Account security, audit activity and support."}].map(({icon:Icon,title,copy}) => <div key={title} className="rounded-2xl bg-[#f7f9f7] p-4"><Icon size={17} className="text-[#285b55]"/><p className="mt-3 text-sm font-black">{title}</p><p className="mt-1 text-[11px] leading-5 text-[#718078]">{copy}</p></div>)}
          </div>
        </section>
      </section>
    </main>
  );
}
