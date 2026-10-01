"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  Cpu,
  Database,
  Globe2,
  HardDrive,
  Mail,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Plan = {
  code: string;
  name: string;
  description: string;
  currency: string;
  monthly_price_minor: number;
  annual_price_minor?: number | null;
  setup_fee_minor: number;
  included_mailboxes: number;
  included_domains: number;
  included_storage_mb: number;
  max_api_keys: number;
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_memory_mb_per_project: number;
  hosting_cpu_millicores_per_project: number;
  hosting_pids_per_project: number;
  hosting_database_limit: number;
  hosting_database_storage_mb: number;
  hosting_source_storage_mb: number;
  support_level: string;
  featured: boolean;
  sort_order: number;
};

const money = (minor?: number | null) =>
  minor == null ? "—" : `M ${(minor / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

const gb = (mb: number) => {
  const value = mb / 1024;
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)} GB`;
};

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/public/hosting-pricing`, { cache: "no-store" });
      if (!response.ok) throw new Error("Unable to load hosting packages.");
      const body = await response.json();
      setPlans(body.items || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load hosting packages.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const lowestAnnual = plans
    .map((plan) => plan.annual_price_minor)
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => a - b)[0];

  return <main className="min-h-screen bg-[#f4f6f4] text-[#21342a]">
    <header className="border-b border-white/10 bg-[#123a38] text-white">
      <div className="mx-auto flex max-w-[1320px] items-center justify-between gap-4 px-5 py-5 sm:px-8">
        <Link href="/" className="flex items-center gap-3 font-black"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[#123a38]">!I</span>Ithute Solutions</Link>
        <div className="flex items-center gap-2">
          <Link href="/login" className="rounded-lg border border-white/20 px-4 py-2 text-xs font-bold">Sign in</Link>
          <Link href="/signup" className="rounded-lg bg-[#d8c56a] px-4 py-2 text-xs font-black text-[#123a38]">Get started</Link>
        </div>
      </div>
    </header>

    <section className="mx-auto max-w-[1320px] px-5 py-14 sm:px-8 lg:py-16">
      <div className="mx-auto max-w-4xl text-center">
        <p className="text-[10px] font-black uppercase tracking-[.16em] text-[#718078]">Ithute managed hosting</p>
        <h1 className="mt-3 text-4xl font-black tracking-[-.045em] sm:text-5xl">One clear package family.<br/><span className="text-[#285b55]">Upgrade capacity when you need it.</span></h1>
        <p className="mx-auto mt-5 max-w-3xl text-sm leading-7 text-[#718078]">Every package includes professional email, managed DNS, automatic HTTPS, Git/ZIP deployment, build and runtime logs, managed databases, backups and the Ithute Control Centre.</p>
        {lowestAnnual != null ? <p className="mt-4 text-sm font-black text-[#123a38]">Hosting starts from {money(lowestAnnual)} / year.</p> : null}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link href="#packages" className="rounded-xl bg-[#123a38] px-5 py-3 text-xs font-black text-white">Compare packages</Link>
          <Link href="/signup" className="inline-flex items-center gap-2 px-3 py-3 text-xs font-black text-[#285b55]">Create company account <ArrowRight size={14}/></Link>
        </div>
      </div>

      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          [Mail, "Professional email", "Business mailboxes managed alongside your hosting account."],
          [Database, "MySQL + PostgreSQL", "Managed databases with package limits and backup support."],
          [Globe2, "DNS + HTTPS", "Managed DNS with domain routing and automatic TLS after propagation."],
          [ShieldCheck, "Managed platform", "No root VPS access required; resources are enforced per package."],
        ].map(([Icon, title, copy]) => {
          const I = Icon as typeof Mail;
          return <article key={String(title)} className="rounded-2xl border border-[#dfe6e2] bg-white p-5"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><I size={18}/></div><h2 className="mt-3 text-sm font-black">{String(title)}</h2><p className="mt-1 text-[11px] leading-5 text-[#718078]">{String(copy)}</p></article>;
        })}
      </div>

      <div id="packages" className="scroll-mt-8">
        {loading ? <div className="mt-10 flex items-center justify-center gap-2 text-sm text-[#718078]"><RefreshCw size={15} className="animate-spin"/>Loading packages…</div> : null}
        {error ? <div className="mx-auto mt-10 max-w-xl rounded-2xl border border-red-200 bg-red-50 p-5 text-center text-sm font-bold text-red-700">{error}<button onClick={()=>void load()} className="ml-2 underline">Retry</button></div> : null}
        {!loading && !error ? <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{plans.map((plan) => {
          const annual = plan.annual_price_minor;
          const monthlyEquivalent = annual != null ? annual / 12 : plan.monthly_price_minor;
          return <article key={plan.code} className={`relative flex flex-col overflow-hidden rounded-[28px] border bg-white p-6 shadow-sm ${plan.featured ? "border-[#d8c56a] ring-2 ring-[#d8c56a]/20" : "border-[#dfe6e2]"}`}>
            {plan.featured ? <div className="absolute right-0 top-0 rounded-bl-2xl bg-[#d8c56a] px-4 py-2 text-[9px] font-black uppercase tracking-[.1em] text-[#123a38]">Recommended</div> : null}

            <div>
              <p className="text-[9px] font-black uppercase tracking-[.14em] text-[#718078]">Website & application hosting</p>
              <h2 className="mt-2 text-2xl font-black tracking-[-.035em]">{plan.name}</h2>
              <p className="mt-2 min-h-[44px] text-[11px] leading-5 text-[#718078]">{plan.description}</p>
              <div className="mt-5">
                <p className="text-3xl font-black">{annual != null ? money(annual) : money(plan.monthly_price_minor)}<span className="text-xs font-bold text-[#819087]"> {annual != null ? "/ year" : "/ month"}</span></p>
                {annual != null ? <p className="mt-1 text-[10px] text-[#819087]">Equivalent to {money(monthlyEquivalent)} / month</p> : null}
                <p className="mt-1 text-[10px] font-bold text-[#806b1c]">Setup fee: {money(plan.setup_fee_minor)}</p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-2 text-[10px]">
              <Spec icon={HardDrive} label="App storage" value={gb(plan.hosting_storage_mb)}/>
              <Spec icon={Mail} label="Email accounts" value={String(plan.included_mailboxes)}/>
              <Spec icon={Server} label="Websites/apps" value={String(plan.included_hosted_projects)}/>
              <Spec icon={Database} label="Databases" value={String(plan.hosting_database_limit)}/>
              <Spec icon={Globe2} label="Managed domains" value={String(plan.included_domains)}/>
              <Spec icon={Cpu} label="RAM per app" value={`${plan.hosting_memory_mb_per_project} MB`}/>
            </div>

            <div className="mt-5 rounded-2xl bg-[#f7f9f7] p-4">
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[#718078]">Included in every package</p>
              <ul className="mt-3 space-y-2 text-[11px] text-[#42554b]">
                {["Managed DNS + automatic HTTPS","Git and ZIP deployment","Build and runtime logs","MySQL or PostgreSQL","Database backup support","Ithute Control Centre","Initial setup assistance"].map((item)=><li key={item} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-emerald-600"/><span>{item}</span></li>)}
              </ul>
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-[#e4e9e6] pt-4 text-[10px]"><span><b className="capitalize">{plan.support_level}</b> support</span><span>{gb(plan.hosting_database_storage_mb)} DB storage</span></div>
            <Link href={`/choose-package?plan=${encodeURIComponent(plan.code)}`} className="mt-6 flex w-full items-center justify-center rounded-xl bg-[#123a38] px-4 py-3 text-sm font-black text-white">Choose {plan.name}</Link>
          </article>;
        })}</div> : null}
      </div>

      <section className="mt-12 grid gap-4 lg:grid-cols-[1.1fr_.9fr]">
        <article className="rounded-3xl border border-[#dfe6e2] bg-white p-6"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Need more capacity?</p><h2 className="mt-2 text-2xl font-black tracking-[-.03em]">Keep your package and add only what you need.</h2><p className="mt-3 text-xs leading-6 text-[#718078]">Extra mailboxes, application storage, websites, databases, database storage, domains and source storage can be added without creating conflicting package families.</p></article>
        <article className="rounded-3xl bg-[#123a38] p-6 text-white"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#f1de8b]">Capacity protection</p><h2 className="mt-2 text-xl font-black">Every plan remains enforced server-side.</h2><p className="mt-2 text-xs leading-6 text-white/65">Storage, RAM, CPU, process, database and project limits come from the same owner-managed catalogue shown here. Customer add-ons increase those entitlements through the same control plane.</p></article>
      </section>
    </section>
  </main>;
}

function Spec({icon: Icon,label,value}:{icon:typeof Server;label:string;value:string}) {
  return <div className="rounded-xl border border-[#e4e9e6] p-3"><Icon size={14} className="text-[#285b55]"/><p className="mt-2 text-[9px] font-black uppercase tracking-[.08em] text-[#8a9891]">{label}</p><b className="mt-1 block text-[12px]">{value}</b></div>;
}
