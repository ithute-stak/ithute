import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Building2,
  CheckCircle2,
  CircleAlert,
  CircleDollarSign,
  Database,
  Globe2,
  Headphones,
  KeyRound,
  Mail,
  Network,
  Route,
  Server,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from "lucide-react";

type Health = "good" | "bad" | "warn";
type MetricTone = "emerald" | "amber" | "slate" | "pine";

type NextAction = {
  title: string;
  copy: string;
  href: string;
  label: string;
};

const controlAreas = [
  ["Organisation", "Companies, memberships, users and access boundaries.", "/organizations", Building2, ["Profile", "Team", "Roles"]],
  ["Hosting", "Create projects, deploy source, manage environment, inspect runtime and logs.", "/hosting", Server, ["Projects", "Deploy", "Runtime"]],
  ["Domains & DNS", "Verify domains, manage authoritative DNS records and DNS security.", "/domains", Globe2, ["Domains", "Records", "DNSSEC"]],
  ["Domain registration & renewals", "Submit and track domain registration, renewal and transfer-in requests under your organisation.", "/domain-orders", Globe2, ["Register", "Renew", "Transfer"]],
  ["Connect domain to app", "Route a verified hostname to a running application through Ithute edge with automatic HTTPS.", "/edge-routing", Route, ["Routing", "Caddy", "HTTPS"]],
  ["Databases & backups", "Manage application databases, source resources, database backups and restore operations.", "/hosting-resources", Database, ["PostgreSQL", "MySQL", "Backups"]],
  ["Professional email", "Create mailboxes, use webmail, manage transactional email, delivery and queues.", "/mailboxes", Mail, ["Mailboxes", "Webmail", "SMTP"]],
  ["Billing & package", "View subscription state, invoices, usage and payment recovery controls.", "/billing", CircleDollarSign, ["Package", "Invoices", "Usage"]],
  ["Add-ons & capacity", "Request extra mailboxes, domains, applications, databases and storage without changing the base package.", "/addons", Server, ["Capacity", "Add-ons", "Upgrade"]],
  ["API access", "Scoped credentials for integrations and controlled automation.", "/api-access", KeyRound, ["Keys", "Scopes", "Integrations"]],
  ["Security & audit", "Security controls, platform identity and traceable operational activity.", "/security", ShieldCheck, ["Identity", "Audit", "Controls"]],
  ["Notifications & support", "Operational notifications, assistance and support requests.", "/notifications", Bell, ["Alerts", "Support", "Status"]],
] as const;

function MetricCard({ label, value, detail, icon, tone = "slate" }: { label: string; value: ReactNode; detail: string; icon: ReactNode; tone?: MetricTone }) {
  const tones: Record<MetricTone, string> = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
    slate: "bg-slate-50 text-slate-600 ring-slate-100",
    pine: "bg-[#edf5f2] text-[#184d47] ring-[#d9e9e4]",
  };

  return (
    <article className="rounded-2xl border border-[#e2e9e5] bg-white p-4 shadow-[0_8px_26px_rgba(25,55,42,0.045)] sm:p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#819087]">{label}</p>
          <div className="mt-2 text-[28px] font-black leading-none tracking-[-0.04em] text-[#193027]">{value}</div>
        </div>
        <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ring-1 ${tones[tone]}`}>{icon}</div>
      </div>
      <p className="mt-3 text-[11px] leading-4 text-[#77867e]">{detail}</p>
    </article>
  );
}

export function ControlCentreOverview({
  health,
  firstName,
  loading,
  tenantCount,
  domainCount,
  verifiedCount,
  dnsReady,
  verificationProgress,
  nextAction,
}: {
  health: Health;
  firstName: string;
  loading: boolean;
  tenantCount: number;
  domainCount: number;
  verifiedCount: number;
  dnsReady: number;
  verificationProgress: number;
  nextAction: NextAction;
}) {
  return (
    <>
      <section className="relative overflow-hidden rounded-[28px] border border-[#214f49] bg-[linear-gradient(135deg,#113d39_0%,#174b45_48%,#0e302e_100%)] px-5 py-6 text-white shadow-[0_20px_55px_rgba(18,58,56,0.18)] sm:px-7 sm:py-8 lg:px-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full border border-white/10 bg-white/[0.035]" />
        <div className="pointer-events-none absolute -bottom-32 right-24 h-64 w-64 rounded-full border border-[#d8c56a]/20 bg-[#d8c56a]/[0.045]" />
        <div className="relative z-10 flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.08] px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.13em] text-[#dfeae6]"><Network size={12} /> Ithute Control Centre</span>
              <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.1em] ${health === "good" ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-200" : health === "bad" ? "border-rose-300/30 bg-rose-300/10 text-rose-200" : "border-amber-300/30 bg-amber-300/10 text-amber-200"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${health === "good" ? "bg-emerald-300" : health === "bad" ? "bg-rose-300" : "bg-amber-300"}`} />
                {health === "good" ? "Platform operational" : health === "bad" ? "Control plane unavailable" : "Checking platform"}
              </span>
            </div>
            <p className="mt-6 text-[11px] font-bold uppercase tracking-[0.18em] text-[#b9ccc6]">Organisation & service operations</p>
            <h1 className="mt-2 max-w-2xl text-[32px] font-black leading-[1.08] tracking-[-0.04em] sm:text-[40px]">Welcome, {firstName}.</h1>
            <p className="mt-3 max-w-2xl text-[13px] leading-6 text-[#cad9d5] sm:text-[14px]">Manage your hosting, deployments, databases, backups, domains, DNS, application routing, email, add-ons, billing, security and support from one client portal.</p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <Link href="/onboarding" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.08] px-4 text-[12px] font-extrabold text-white"><Sparkles size={15} /> Setup guide</Link>
            <Link href="/hosting" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#d8c56a] px-4 text-[12px] font-black text-[#173c36]">Manage services <ArrowRight size={15} /></Link>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Organisations" value={loading ? "-" : tenantCount} detail="Active organisation contexts" tone={tenantCount ? "emerald" : "amber"} icon={<Building2 size={18} />} />
        <MetricCard label="Domains" value={loading ? "-" : domainCount} detail="Across accessible organisations" tone="pine" icon={<Globe2 size={18} />} />
        <MetricCard label="Verified" value={loading ? "-" : verifiedCount} detail={`${verificationProgress}% of known domains`} tone={verifiedCount ? "emerald" : "amber"} icon={<CheckCircle2 size={18} />} />
        <MetricCard label="DNS ready" value={loading ? "-" : dnsReady} detail="Verified and on platform DNS" tone={dnsReady ? "emerald" : "slate"} icon={<Server size={18} />} />
        <MetricCard label="Control plane" value={<span className={`inline-flex items-center gap-2 text-[16px] ${health === "good" ? "text-emerald-700" : health === "bad" ? "text-rose-700" : "text-amber-700"}`}>{health === "good" ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}{health === "good" ? "Operational" : health === "bad" ? "Unavailable" : "Checking"}</span>} detail="Live readiness probe" tone={health === "good" ? "emerald" : "amber"} icon={<Activity size={18} />} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.4fr_.6fr]">
        <div className="rounded-[24px] border border-[#e1e8e4] bg-white p-5 shadow-[0_10px_34px_rgba(28,55,44,.05)] sm:p-6">
          <div className="flex items-end justify-between gap-3">
            <div><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Client service controls</p><h2 className="mt-2 text-xl font-black tracking-[-.035em] text-[#20342a]">Everything your organisation can manage through Ithute.</h2><p className="mt-2 max-w-3xl text-[11px] leading-5 text-[#718078]">The portal exposes day-to-day self-service while the backend still enforces your package, permissions, approval state, billing/grace state, quotas and tenant isolation.</p></div>
            <Link href="/status" className="hidden items-center gap-2 text-[11px] font-black text-[#285b55] sm:inline-flex">Service status <ArrowRight size={13} /></Link>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {controlAreas.map(([title, copy, href, Icon, tags]) => (
              <Link key={title} href={href} className="group rounded-2xl border border-[#e1e8e4] bg-[#fafcfa] p-4 transition hover:bg-white hover:shadow-lg hover:shadow-[#123a38]/5">
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#edf4f1] text-[#174b45]"><Icon size={17} /></div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-black text-[#20342a]">{title}</h3><ArrowRight size={14} className="text-[#9aa8a1]" /></div>
                    <p className="mt-1.5 text-[10px] leading-5 text-[#77867e]">{copy}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">{tags.map((tag) => <span key={tag} className="rounded-full border border-[#e2e9e5] bg-white px-2 py-1 text-[8px] font-bold text-[#718078]">{tag}</span>)}</div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <article className="rounded-[24px] border border-[#d8c56a]/40 bg-[linear-gradient(145deg,#fffdf1,#fff)] p-5 shadow-sm">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#efe4a4] text-[#123a38]"><Sparkles size={18} /></div>
            <p className="mt-5 text-[9px] font-black uppercase tracking-[.14em] text-[#7f7441]">Recommended next action</p>
            <h2 className="mt-2 text-lg font-black text-[#20342a]">{nextAction.title}</h2>
            <p className="mt-2 text-[11px] leading-5 text-[#718078]">{nextAction.copy}</p>
            <Link href={nextAction.href} className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl bg-[#123a38] px-4 text-[11px] font-black text-white">{nextAction.label} <ArrowRight size={13} /></Link>
          </article>
          <article className="rounded-[24px] border border-[#e1e8e4] bg-white p-5 shadow-sm">
            <p className="text-[9px] font-black uppercase tracking-[.14em] text-[#718078]">Quick access</p>
            <div className="mt-4 space-y-2">
              {[[Globe2, "Domain registration & renewals", "/domain-orders"], [Route, "Connect domain to app", "/edge-routing"], [Server, "Add-ons & capacity", "/addons"], [Mail, "Open Webmail", "/webmail"], [Headphones, "Support centre", "/support"], [UsersRound, "Team access", "/organizations"], [ShieldCheck, "Security", "/security"]].map(([Icon, label, href]) => {
                const ItemIcon = Icon as typeof Mail;
                return <Link key={String(label)} href={String(href)} className="flex items-center gap-3 rounded-xl border border-[#e7ece9] px-3 py-2.5 text-[11px] font-bold text-[#51675e]"><ItemIcon size={14} /><span className="flex-1">{String(label)}</span><ArrowRight size={12} /></Link>;
              })}
            </div>
          </article>
        </div>
      </section>
    </>
  );
}
