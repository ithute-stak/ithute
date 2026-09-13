"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  Cpu,
  FileText,
  Globe2,
  HardDrive,
  Mail,
  Palette,
  PenTool,
  Server,
  ShieldCheck,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Plan = {
  code: string;
  name: string;
  monthly_price_minor: number;
  included_mailboxes: number;
  included_domains: number;
  included_storage_mb: number;
  max_api_keys: number;
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_memory_mb_per_project: number;
  hosting_cpu_millicores_per_project: number;
  hosting_pids_per_project: number;
  product_category: string;
  description: string;
  website_pages: number;
  includes_website_design: boolean;
  includes_logo_design: boolean;
  includes_brand_guide: boolean;
  includes_company_profile: boolean;
  includes_letterhead: boolean;
  includes_page_headers_footers: boolean;
  includes_business_templates: boolean;
  included_revisions: number;
  content_updates_per_month: number;
  support_level: string;
  minimum_term_months: number;
  price_from: boolean;
};

function creativeBenefits(plan: Plan) {
  const benefits: string[] = [];
  if (plan.includes_website_design) benefits.push(plan.website_pages ? `Responsive website design — up to ${plan.website_pages} page${plan.website_pages === 1 ? "" : "s"}` : "Responsive website design");
  if (plan.includes_logo_design) benefits.push("Logo design / brand mark setup");
  if (plan.includes_page_headers_footers) benefits.push("Branded page headers & footers");
  if (plan.includes_brand_guide) benefits.push("Brand colours, typography & identity guide");
  if (plan.includes_company_profile) benefits.push("Company profile / corporate profile design");
  if (plan.includes_letterhead) benefits.push("Professional letterhead design");
  if (plan.includes_business_templates) benefits.push("Quotation, invoice & business document templates");
  if (plan.included_revisions) benefits.push(`${plan.included_revisions} initial design revision${plan.included_revisions === 1 ? "" : "s"}`);
  if (plan.content_updates_per_month) benefits.push(`${plan.content_updates_per_month} content update${plan.content_updates_per_month === 1 ? "" : "s"} per month`);
  return benefits;
}

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetch(`${API}/public/hosting-pricing`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((body) => setPlans(body.items || []))
      .finally(() => setLoading(false));
  }, []);

  return <main className="min-h-screen bg-[#f4f6f4] text-[#21342a]">
    <header className="border-b border-[#dfe6e2] bg-[#123a38] text-white"><div className="mx-auto flex max-w-[1320px] items-center justify-between gap-4 px-5 py-5 sm:px-8"><Link href="/" className="flex items-center gap-3 font-black"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[#123a38]">!I</span>Ithute Solutions</Link><div className="flex items-center gap-2"><Link href="/hosting-docs" className="hidden px-3 py-2 text-xs font-bold text-white/70 hover:text-white sm:inline">Hosting rules</Link><Link href="/login" className="rounded-lg border border-white/20 px-4 py-2 text-xs font-bold">Sign in</Link><Link href="/signup" className="rounded-lg bg-[#d8c56a] px-4 py-2 text-xs font-black text-[#123a38]">Get started</Link></div></div></header>

    <section className="mx-auto max-w-[1320px] px-5 py-14 sm:px-8 lg:py-16">
      <div className="mx-auto max-w-4xl text-center"><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Website · branding · documents · hosting · email</p><h1 className="mt-3 text-4xl font-black tracking-[-.04em] sm:text-5xl">Your business online from <span className="text-[#285b55]">M185/month.</span></h1><p className="mx-auto mt-5 max-w-3xl text-sm leading-7 text-[#718078]">Ithute does more than sell server space. We can build the website, prepare the brand, create professional business documents, host the site, manage DNS and provide company email in one predictable monthly package.</p><div className="mt-6 flex flex-wrap items-center justify-center gap-3"><Link href="#packages" className="rounded-xl bg-[#123a38] px-5 py-3 text-xs font-black text-white">Compare packages</Link><Link href="/hosting-docs" className="inline-flex items-center gap-2 px-3 py-3 text-xs font-black text-[#285b55]"><BookOpen size={15}/>Hosting rules <ArrowRight size={14}/></Link></div></div>

      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[{icon: PenTool,title:"Website creation",copy:"Responsive business websites designed and managed by Ithute."},{icon: Palette,title:"Brand identity",copy:"Logos, colours, typography and brand documentation by package."},{icon: FileText,title:"Business documents",copy:"Letterheads, page headers/footers, company profiles and templates."},{icon: ShieldCheck,title:"Managed infrastructure",copy:"Hosting, SSL, DNS, resource isolation and professional email."}].map(({icon: Icon,title,copy}) => <article key={title} className="rounded-2xl border border-[#dfe6e2] bg-white p-5"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Icon size={18}/></div><h2 className="mt-3 text-sm font-black">{title}</h2><p className="mt-1 text-[11px] leading-5 text-[#718078]">{copy}</p></article>)}
      </div>

      <div id="packages" className="scroll-mt-8">
        {loading ? <div className="mt-10 text-center text-sm text-[#718078]">Loading Ithute packages…</div> : <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{plans.map((plan) => {
          const appStorageGb = plan.hosting_storage_mb / 1024;
          const mailStorageGb = plan.included_storage_mb / 1024;
          const benefits = creativeBenefits(plan);
          const featured = plan.code === "business";
          return <article key={plan.code} className={`relative flex flex-col overflow-hidden rounded-3xl border bg-white p-6 shadow-sm ${featured ? "border-[#d8c56a] ring-2 ring-[#d8c56a]/25" : "border-[#dfe6e2]"}`}>
            {featured ? <div className="absolute right-0 top-0 rounded-bl-2xl bg-[#d8c56a] px-4 py-2 text-[9px] font-black uppercase tracking-[.1em] text-[#123a38]">Popular SME package</div> : null}
            <div><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">{plan.product_category}</p><h2 className="mt-2 text-xl font-black">{plan.name}</h2><p className="mt-2 min-h-[44px] text-[11px] leading-5 text-[#718078]">{plan.description}</p><p className="mt-5 text-3xl font-black">{plan.price_from ? "From " : ""}M {(plan.monthly_price_minor / 100).toLocaleString()}<span className="text-xs font-bold text-[#819087]"> / month</span></p>{plan.minimum_term_months > 1 ? <p className="mt-1 text-[9px] font-bold text-[#8a7650]">Creative build included on a {plan.minimum_term_months}-month agreement.</p> : null}</div>

            <div className="mt-6 rounded-2xl bg-[#f7f9f7] p-4"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[#718078]">Creative & business deliverables</p><ul className="mt-3 space-y-2 text-[11px]">{benefits.map((benefit) => <li key={benefit} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-emerald-600"/><span>{benefit}</span></li>)}{!benefits.length ? <li className="text-[#718078]">Managed hosting package; creative work scoped separately.</li> : null}</ul></div>

            <div className="mt-5"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[#718078]">Hosting included</p><div className="mt-3 grid grid-cols-2 gap-2 text-[10px]"><div className="rounded-xl border border-[#e4e9e6] p-3"><Server size={14} className="text-[#285b55]"/><b className="mt-1 block">{plan.included_hosted_projects} project{plan.included_hosted_projects === 1 ? "" : "s"}</b></div><div className="rounded-xl border border-[#e4e9e6] p-3"><HardDrive size={14} className="text-[#285b55]"/><b className="mt-1 block">{appStorageGb.toFixed(appStorageGb % 1 ? 1 : 0)} GB app</b></div><div className="rounded-xl border border-[#e4e9e6] p-3"><Globe2 size={14} className="text-[#285b55]"/><b className="mt-1 block">{plan.included_domains} domains</b></div><div className="rounded-xl border border-[#e4e9e6] p-3"><Mail size={14} className="text-[#285b55]"/><b className="mt-1 block">{plan.included_mailboxes} mailboxes</b><span className="text-[9px] text-[#819087]">{mailStorageGb.toFixed(mailStorageGb % 1 ? 1 : 0)} GB mail pool</span></div></div><div className="mt-2 flex items-center gap-2 rounded-xl border border-[#e4e9e6] p-3 text-[10px]"><Cpu size={14} className="shrink-0 text-[#285b55]"/><span><b>{plan.hosting_memory_mb_per_project} MB RAM · {(plan.hosting_cpu_millicores_per_project / 1000).toFixed(2)} CPU/project</b> · {plan.hosting_pids_per_project} process limit</span></div></div>

            <div className="mt-5 flex items-center justify-between border-t border-[#e4e9e6] pt-4 text-[10px]"><span><b className="capitalize">{plan.support_level}</b> support</span>{plan.content_updates_per_month ? <span>{plan.content_updates_per_month} updates/mo</span> : <span>Hosting maintenance included</span>}</div>
            <Link href={`/signup?plan=${plan.code}`} className="mt-6 flex w-full items-center justify-center rounded-xl bg-[#123a38] px-4 py-3 text-sm font-black text-white">Choose {plan.name}</Link>
          </article>;
        })}</div>}
      </div>

      <section className="mt-12 grid gap-4 lg:grid-cols-[1.1fr_.9fr]"><article className="rounded-3xl border border-[#dfe6e2] bg-white p-6"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">What the monthly model means</p><h2 className="mt-2 text-2xl font-black tracking-[-.03em]">A real service package, not unlimited design labour.</h2><p className="mt-3 text-xs leading-6 text-[#718078]">The initial website and creative deliverables are defined by the selected package. Revision allowances and monthly content updates are explicit, so customers know exactly what is included and Ithute can maintain quality without promising unlimited redesign work.</p></article><article className="rounded-3xl bg-[#123a38] p-6 text-white"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#f1de8b]">Managed hosting protection</p><h2 className="mt-2 text-xl font-black">Every site still runs inside enforced capacity.</h2><p className="mt-2 text-xs leading-6 text-white/65">Monthly creative services do not weaken the hosting rules. Project storage, RAM, CPU and process limits remain enforced, and customers do not receive root VPS, host SSH, privileged-container or Docker-socket access.</p><Link href="/hosting-docs" className="mt-4 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-3 text-xs font-black text-[#123a38]"><BookOpen size={15}/>Read hosting rules</Link></article></section>
    </section>
  </main>;
}
