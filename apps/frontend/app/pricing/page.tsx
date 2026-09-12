"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  DatabaseBackup,
  Globe2,
  KeyRound,
  Mail,
  Network,
  Server,
  ShieldCheck,
  Smartphone,
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
};

const commonFeatures = [
  { icon: Network, title: "Authoritative DNS + DNSSEC", copy: "Host official DNS zones on the platform and protect signed zones with DNSSEC." },
  { icon: Smartphone, title: "Webmail + IMAP/SMTP", copy: "Use browser Webmail or standards-based clients such as Outlook, phones and Thunderbird." },
  { icon: ShieldCheck, title: "SPF, DKIM & DMARC tooling", copy: "Configure sender authentication, signing, anti-spoofing policy and deliverability controls." },
  { icon: DatabaseBackup, title: "Encrypted backups + monitoring", copy: "Protected operational backups plus service-health monitoring and alerting." },
];

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetch(`${API}/public/pricing`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((body) => setPlans(body.items || []))
      .finally(() => setLoading(false));
  }, []);

  return <main className="min-h-screen bg-[#f4f6f4] text-[#21342a]">
    <header className="border-b border-[#dfe6e2] bg-[#123a38] text-white"><div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-5 py-5 sm:px-8"><Link href="/" className="flex items-center gap-3 font-black"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[#123a38]">MD</span>Mailbox DNS</Link><div className="flex items-center gap-2"><Link href="/docs" className="hidden px-3 py-2 text-xs font-bold text-white/70 hover:text-white sm:inline">Documentation</Link><Link href="/login" className="rounded-lg border border-white/20 px-4 py-2 text-xs font-bold">Sign in</Link><Link href="/signup" className="rounded-lg bg-[#d8c56a] px-4 py-2 text-xs font-black text-[#123a38]">Start free trial</Link></div></div></header>

    <section className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 lg:py-16">
      <div className="mx-auto max-w-3xl text-center"><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Business email + DNS</p><h1 className="mt-3 text-4xl font-black tracking-[-.04em]">Choose capacity you can understand.</h1><p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-[#718078]">Each package sets real limits for mailboxes, hosted domains, storage and API access. Core DNS, mail security, Webmail, backups and monitoring are included in every active package.</p><Link href="/docs#packages" className="mt-5 inline-flex items-center gap-2 text-xs font-black text-[#285b55]"><BookOpen size={15}/>Read exactly what every item means <ArrowRight size={14}/></Link></div>

      {loading ? <div className="mt-10 text-center text-sm text-[#718078]">Loading packages…</div> : <div className="mt-10 grid gap-5 lg:grid-cols-3">{plans.map((plan, index) => {
        const storageGb = Math.round(plan.included_storage_mb / 1000);
        const quotas = [
          { icon: Mail, value: `${plan.included_mailboxes} mailboxes`, copy: "Individual email accounts your organization can create." },
          { icon: Globe2, value: `${plan.included_domains} hosted domains`, copy: "Different domains you can onboard under this subscription." },
          { icon: Server, value: `${storageGb} GB allocated storage`, copy: "Shared mailbox quota pool across the organization—not per mailbox." },
          { icon: KeyRound, value: `${plan.max_api_keys} API keys`, copy: "Active credentials for integrations and automation." },
        ];
        return <article key={plan.code} className={`flex flex-col rounded-3xl border bg-white p-6 shadow-sm ${index === 1 ? "border-[#d8c56a] ring-2 ring-[#d8c56a]/20" : "border-[#dfe6e2]"}`}>
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[.1em] text-[#718078]">{plan.name}</p><p className="mt-2 text-3xl font-black">M {(plan.monthly_price_minor / 100).toLocaleString()}<span className="text-xs font-bold text-[#819087]"> / month</span></p></div><ShieldCheck className="text-[#285b55]" size={24}/></div>
          <div className="mt-6 space-y-3">{quotas.map(({icon: Icon,value,copy}) => <div key={value} className="rounded-xl border border-[#e4e9e6] bg-[#fafbfa] p-3"><div className="flex items-center gap-2"><Icon size={15} className="shrink-0 text-[#285b55]"/><p className="text-xs font-black text-[#263a31]">{value}</p></div><p className="mt-1 pl-[23px] text-[10px] leading-4 text-[#718078]">{copy}</p></div>)}</div>
          <div className="mt-5 border-t border-[#e4e9e6] pt-5"><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#819087]">Included in this package</p><ul className="mt-3 space-y-2 text-[11px]">{commonFeatures.map(({title}) => <li key={title} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-emerald-600"/><span>{title}</span></li>)}</ul></div>
          <Link href={`/signup?plan=${plan.code}`} className="mt-7 flex w-full items-center justify-center rounded-xl bg-[#123a38] px-4 py-3 text-sm font-black text-white">Choose {plan.name}</Link>
        </article>;
      })}</div>}

      <section className="mt-12"><div className="max-w-2xl"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Included services</p><h2 className="mt-2 text-2xl font-black tracking-[-.03em]">What the technical features actually do</h2><p className="mt-2 text-xs leading-6 text-[#718078]">These capabilities are platform services. The numeric differences between packages control capacity, while these core services are available across the catalog.</p></div><div className="mt-6 grid gap-4 sm:grid-cols-2">{commonFeatures.map(({icon: Icon,title,copy}) => <article key={title} className="rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Icon size={18}/></div><h3 className="mt-4 text-sm font-black">{title}</h3><p className="mt-2 text-[11px] leading-5 text-[#718078]">{copy}</p></article>)}</div></section>

      <section className="mt-10 rounded-3xl bg-[#123a38] p-6 text-white sm:p-7"><div className="grid gap-5 md:grid-cols-[1fr_auto] md:items-center"><div><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#f1de8b]">Before you buy</p><h2 className="mt-2 text-xl font-black">Read the configuration manual, not just the price.</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-white/65">The documentation explains domain verification, nameserver delegation, DNSSEC, MX/SPF/DKIM/DMARC, email-client settings, API keys, backups and security so your team knows what is included and what must be configured.</p></div><Link href="/docs" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-xs font-black text-[#123a38]"><BookOpen size={15}/>Open documentation</Link></div></section>

      <div className="mt-6 rounded-2xl bg-[#eaf2ef] p-5 text-sm"><div className="flex gap-3"><Mail className="shrink-0 text-[#285b55]" size={20}/><div><p className="font-black">Need migration help or capacity beyond the published catalog?</p><p className="mt-1 text-[#617168]">Create an account and open a support request for migration assistance or a tailored commercial plan.</p></div></div></div>
    </section>
  </main>;
}
