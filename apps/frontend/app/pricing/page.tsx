"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  Cpu,
  DatabaseBackup,
  Globe2,
  HardDrive,
  Mail,
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
};

const commonFeatures = [
  { icon: Server, title: "Managed application hosting", copy: "Host websites and simple business systems in isolated, resource-limited workloads on Ithute infrastructure." },
  { icon: Globe2, title: "Authoritative DNS + HTTPS routing", copy: "Manage domains in Ithute DNS and route verified hostnames through the platform edge instead of exposing customer containers directly." },
  { icon: Mail, title: "Professional email", copy: "Packages can include business mailboxes, Webmail and standards-based IMAP/SMTP alongside application hosting." },
  { icon: ShieldCheck, title: "Mandatory workload isolation", copy: "No customer root access, host SSH, privileged containers or Docker socket access on shared hosting nodes." },
  { icon: DatabaseBackup, title: "Backup and operations foundation", copy: "Project allocations integrate with Ithute monitoring, audit and the platform backup lifecycle as hosting capabilities expand." },
];

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
    <header className="border-b border-[#dfe6e2] bg-[#123a38] text-white"><div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-5 py-5 sm:px-8"><Link href="/" className="flex items-center gap-3 font-black"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[#123a38]">!I</span>Ithute Hosting</Link><div className="flex items-center gap-2"><Link href="/hosting-docs" className="hidden px-3 py-2 text-xs font-bold text-white/70 hover:text-white sm:inline">Hosting rules</Link><Link href="/login" className="rounded-lg border border-white/20 px-4 py-2 text-xs font-bold">Sign in</Link><Link href="/signup" className="rounded-lg bg-[#d8c56a] px-4 py-2 text-xs font-black text-[#123a38]">Start free trial</Link></div></div></header>

    <section className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 lg:py-16">
      <div className="mx-auto max-w-3xl text-center"><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Websites · simple systems · email · DNS</p><h1 className="mt-3 text-4xl font-black tracking-[-.04em]">One package for the services your organization actually runs.</h1><p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-[#718078]">Ithute packages now combine managed application hosting with domains, DNS and optional professional email. Application limits are real quotas: storage, RAM, CPU and process ceilings are enforced to protect every customer sharing the hosting infrastructure.</p><Link href="/hosting-docs" className="mt-5 inline-flex items-center gap-2 text-xs font-black text-[#285b55]"><BookOpen size={15}/>Read the hosting rules before deploying <ArrowRight size={14}/></Link></div>

      {loading ? <div className="mt-10 text-center text-sm text-[#718078]">Loading hosting packages…</div> : <div className="mt-10 grid gap-5 lg:grid-cols-3">{plans.map((plan, index) => {
        const appStorageGb = plan.hosting_storage_mb / 1024;
        const mailStorageGb = plan.included_storage_mb / 1024;
        const quotas = [
          { icon: Server, value: `${plan.included_hosted_projects} hosted project${plan.included_hosted_projects === 1 ? "" : "s"}`, copy: "Websites or simple business systems allocated to this organization." },
          { icon: HardDrive, value: `${appStorageGb.toFixed(appStorageGb % 1 ? 1 : 0)} GB app storage`, copy: "Shared application storage pool, separate from professional-email storage." },
          { icon: Cpu, value: `${plan.hosting_memory_mb_per_project} MB RAM · ${(plan.hosting_cpu_millicores_per_project / 1000).toFixed(2)} CPU`, copy: `Per-project ceiling with a ${plan.hosting_pids_per_project}-process limit.` },
          { icon: Globe2, value: `${plan.included_domains} hosted domains`, copy: "Verified domains available for DNS, mail and application hostnames." },
          { icon: Mail, value: `${plan.included_mailboxes} mailboxes · ${mailStorageGb.toFixed(mailStorageGb % 1 ? 1 : 0)} GB mail`, copy: plan.included_mailboxes ? "Professional email remains available within the same package." : "This package is application-hosting focused with no included mailboxes." },
        ];
        return <article key={plan.code} className={`flex flex-col rounded-3xl border bg-white p-6 shadow-sm ${index === 1 ? "border-[#d8c56a] ring-2 ring-[#d8c56a]/20" : "border-[#dfe6e2]"}`}>
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[.1em] text-[#718078]">{plan.name}</p><p className="mt-2 text-3xl font-black">M {(plan.monthly_price_minor / 100).toLocaleString()}<span className="text-xs font-bold text-[#819087]"> / month</span></p></div><ShieldCheck className="text-[#285b55]" size={24}/></div>
          <div className="mt-6 space-y-3">{quotas.map(({icon: Icon,value,copy}) => <div key={value} className="rounded-xl border border-[#e4e9e6] bg-[#fafbfa] p-3"><div className="flex items-center gap-2"><Icon size={15} className="shrink-0 text-[#285b55]"/><p className="text-xs font-black text-[#263a31]">{value}</p></div><p className="mt-1 pl-[23px] text-[10px] leading-4 text-[#718078]">{copy}</p></div>)}</div>
          <div className="mt-5 border-t border-[#e4e9e6] pt-5"><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#819087]">Included platform capabilities</p><ul className="mt-3 space-y-2 text-[11px]">{commonFeatures.slice(0,4).map(({title}) => <li key={title} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-emerald-600"/><span>{title}</span></li>)}</ul></div>
          <Link href={`/signup?plan=${plan.code}`} className="mt-7 flex w-full items-center justify-center rounded-xl bg-[#123a38] px-4 py-3 text-sm font-black text-white">Choose {plan.name}</Link>
        </article>;
      })}</div>}

      <section className="mt-12"><div className="max-w-2xl"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Shared-hosting protection</p><h2 className="mt-2 text-2xl font-black tracking-[-.03em]">Hosting capacity is controlled, not merely advertised.</h2><p className="mt-2 text-xs leading-6 text-[#718078]">The system owner first marks only a safe portion of each server as sellable. Ithute then refuses project allocations that would exceed either the customer package or the remaining node capacity.</p></div><div className="mt-6 grid gap-4 sm:grid-cols-2">{commonFeatures.map(({icon: Icon,title,copy}) => <article key={title} className="rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Icon size={18}/></div><h3 className="mt-4 text-sm font-black">{title}</h3><p className="mt-2 text-[11px] leading-5 text-[#718078]">{copy}</p></article>)}</div></section>

      <section className="mt-10 rounded-3xl bg-[#123a38] p-6 text-white sm:p-7"><div className="grid gap-5 md:grid-cols-[1fr_auto] md:items-center"><div><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#f1de8b]">Mandatory before hosting</p><h2 className="mt-2 text-xl font-black">Every hosted system follows the Ithute Hosting Rules.</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-white/65">The rules cover isolation, resource limits, approved builds, domains, email sending, prohibited workloads, databases and secrets. Creating a hosted project requires explicit acceptance of the current rules version.</p></div><Link href="/hosting-docs" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-xs font-black text-[#123a38]"><BookOpen size={15}/>Open hosting rules</Link></div></section>
    </section>
  </main>;
}
