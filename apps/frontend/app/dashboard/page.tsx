"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowRight,
  Building2,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Globe2,
  KeyRound,
  Network,
  Server,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { StatusBadge } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type User = {
  email: string;
  full_name: string;
  is_platform_owner: boolean;
  mfa_enabled: boolean;
};

type Membership = {
  tenant_id: string;
  tenant_name: string;
  status: string;
};

type Domain = {
  status: string;
  dns_mode: string;
  ownership_verified_at?: string | null;
};

type Audit = {
  id: string;
  action: string;
  resource_type?: string | null;
  created_at: string;
};

type Health = "good" | "bad" | "warn";
type MetricTone = "emerald" | "amber" | "slate" | "pine";

async function api(path: string) {
  let response = await fetch(`${API}${path}`, {
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (refresh.ok) {
      response = await fetch(`${API}${path}`, {
        credentials: "include",
        cache: "no-store",
      });
    }
  }

  return response;
}

const modules = [
  {
    title: "Organizations",
    copy: "Companies, memberships and access roles.",
    href: "/organizations",
    icon: Building2,
    accent: "from-emerald-50 to-white",
  },
  {
    title: "Domain portfolio",
    copy: "Ownership, verification and hosting readiness.",
    href: "/domains",
    icon: Globe2,
    accent: "from-sky-50 to-white",
  },
  {
    title: "DNS zones",
    copy: "PowerDNS zones and authoritative record sets.",
    href: "/dns",
    icon: Server,
    accent: "from-violet-50 to-white",
  },
  {
    title: "DNS security",
    copy: "Signing, policy and domain-protection controls.",
    href: "/dns-security",
    icon: ShieldCheck,
    accent: "from-amber-50 to-white",
  },
  {
    title: "API access",
    copy: "Scoped automation credentials and revocation.",
    href: "/api-access",
    icon: KeyRound,
    accent: "from-rose-50 to-white",
  },
  {
    title: "Audit & activity",
    copy: "Searchable activity across infrastructure changes.",
    href: "/audit",
    icon: Activity,
    accent: "from-teal-50 to-white",
  },
];

function MetricCard({
  label,
  value,
  detail,
  icon,
  tone = "slate",
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: ReactNode;
  tone?: MetricTone;
}) {
  const tones: Record<MetricTone, string> = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
    slate: "bg-slate-50 text-slate-600 ring-slate-100",
    pine: "bg-[#edf5f2] text-[#184d47] ring-[#d9e9e4]",
  };

  return (
    <article className="group rounded-2xl border border-[#e2e9e5] bg-white p-4 shadow-[0_8px_26px_rgba(25,55,42,0.045)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_34px_rgba(25,55,42,0.075)] sm:p-5">
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

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [tenantCount, setTenantCount] = useState(0);
  const [domainCount, setDomainCount] = useState(0);
  const [verifiedCount, setVerifiedCount] = useState(0);
  const [dnsReady, setDnsReady] = useState(0);
  const [health, setHealth] = useState<Health>("warn");
  const [audit, setAudit] = useState<Audit[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const meResponse = await api("/auth/me");
        if (!meResponse.ok) {
          router.replace("/login");
          return;
        }

        const me: User = await meResponse.json();
        setUser(me);

        let contexts: Membership[] = [];
        if (me.is_platform_owner) {
          const tenantResponse = await api("/tenants");
          const data = tenantResponse.ok ? await tenantResponse.json() : [];
          contexts = data.map((item: { id: string; name: string; status: string }) => ({
            tenant_id: item.id,
            tenant_name: item.name,
            status: item.status,
          }));
        } else {
          const membershipResponse = await api("/me/memberships");
          contexts = membershipResponse.ok ? await membershipResponse.json() : [];
        }

        const activeContexts = contexts.filter((context) => context.status === "active");
        setTenantCount(activeContexts.length);

        const domains: Domain[] = [];
        for (const context of activeContexts.slice(0, 20)) {
          const domainResponse = await api(`/tenants/${context.tenant_id}/domains`);
          if (domainResponse.ok) {
            const data = await domainResponse.json();
            domains.push(...(data.items || []));
          }
        }

        setDomainCount(domains.length);
        setVerifiedCount(domains.filter((domain) => Boolean(domain.ownership_verified_at)).length);
        setDnsReady(
          domains.filter(
            (domain) =>
              domain.status === "verified" &&
              domain.dns_mode === "platform" &&
              Boolean(domain.ownership_verified_at),
          ).length,
        );

        const auditResponse = me.is_platform_owner
          ? await api("/audit/platform?limit=8")
          : activeContexts[0]
            ? await api(`/tenants/${activeContexts[0].tenant_id}/audit?limit=8`)
            : null;

        if (auditResponse?.ok) setAudit(await auditResponse.json());

        try {
          const healthResponse = await fetch(`${API.replace(/\/api\/v1$/, "")}/health/ready`, {
            cache: "no-store",
          });
          setHealth(healthResponse.ok ? "good" : "bad");
        } catch {
          setHealth("bad");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const verificationProgress = useMemo(
    () => (domainCount ? Math.round((verifiedCount / domainCount) * 100) : 0),
    [domainCount, verifiedCount],
  );

  const readinessProgress = useMemo(() => {
    if (!domainCount) return 0;
    return Math.round((dnsReady / domainCount) * 100);
  }, [dnsReady, domainCount]);

  const firstName = user?.full_name?.trim().split(/\s+/)[0] || (user?.is_platform_owner ? "Platform Owner" : "there");
  const nextAction = domainCount === 0
    ? { title: "Add your first domain", copy: "Start by adding a domain, verifying ownership and choosing platform DNS.", href: "/domains", label: "Add domain" }
    : verifiedCount < domainCount
      ? { title: "Finish domain verification", copy: `${domainCount - verifiedCount} domain${domainCount - verifiedCount === 1 ? "" : "s"} still need ownership verification.`, href: "/domains", label: "Review domains" }
      : dnsReady < domainCount
        ? { title: "Complete DNS onboarding", copy: "Verified domains are ready to be moved onto authoritative platform DNS.", href: "/dns", label: "Configure DNS" }
        : { title: "Platform is ready to scale", copy: "Core domain and DNS onboarding is complete. You can now expand mail and hosting services.", href: "/mailboxes", label: "Open mail platform" };

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[26px] border border-[#214f49] bg-[linear-gradient(135deg,#113d39_0%,#174b45_48%,#0e302e_100%)] px-5 py-6 text-white shadow-[0_20px_55px_rgba(18,58,56,0.18)] sm:px-7 sm:py-7 lg:px-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full border border-white/10 bg-white/[0.035]" />
        <div className="pointer-events-none absolute -bottom-32 right-24 h-64 w-64 rounded-full border border-[#d8c56a]/20 bg-[#d8c56a]/[0.045]" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,.6)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.6)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:linear-gradient(to_right,transparent,black_65%)]" />

        <div className="relative z-10 flex flex-col gap-7 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.08] px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.13em] text-[#dfeae6]">
                <Network size={12} /> Infrastructure command centre
              </span>
              <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.1em] ${health === "good" ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-200" : health === "bad" ? "border-rose-300/30 bg-rose-300/10 text-rose-200" : "border-amber-300/30 bg-amber-300/10 text-amber-200"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${health === "good" ? "bg-emerald-300" : health === "bad" ? "bg-rose-300" : "bg-amber-300"}`} />
                {health === "good" ? "All systems operational" : health === "bad" ? "Control plane unavailable" : "Checking platform"}
              </span>
            </div>

            <p className="mt-6 text-[11px] font-bold uppercase tracking-[0.18em] text-[#b9ccc6]">Mailbox DNS operations</p>
            <h1 className="mt-2 max-w-2xl text-[32px] font-black leading-[1.08] tracking-[-0.04em] text-white sm:text-[38px]">
              Welcome, {firstName}.
            </h1>
            <p className="mt-3 max-w-2xl text-[13px] leading-6 text-[#cad9d5] sm:text-[14px]">
              A live view of your organizations, domains, authoritative DNS and platform security—built for fast operational decisions.
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <Link href="/onboarding" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.08] px-4 text-[12px] font-extrabold text-white transition hover:-translate-y-0.5 hover:bg-white/[0.13]">
              <Sparkles size={15} /> Setup guide
            </Link>
            <Link href="/dns" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#d8c56a] px-4 text-[12px] font-black text-[#173c36] shadow-[0_10px_30px_rgba(0,0,0,0.15)] transition hover:-translate-y-0.5 hover:bg-[#e1d07a]">
              Manage DNS <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Organizations"
          value={loading ? "—" : tenantCount}
          detail="Active company contexts"
          tone={tenantCount ? "emerald" : "amber"}
          icon={<Building2 size={18} />}
        />
        <MetricCard
          label="Domains"
          value={loading ? "—" : domainCount}
          detail="Across accessible organizations"
          tone="pine"
          icon={<Globe2 size={18} />}
        />
        <MetricCard
          label="Verified"
          value={loading ? "—" : verifiedCount}
          detail={`${verificationProgress}% of known domains`}
          tone={verifiedCount ? "emerald" : "amber"}
          icon={<CheckCircle2 size={18} />}
        />
        <MetricCard
          label="DNS ready"
          value={loading ? "—" : dnsReady}
          detail="Verified and on platform DNS"
          tone={dnsReady ? "emerald" : "slate"}
          icon={<Server size={18} />}
        />
        <MetricCard
          label="Control plane"
          value={
            <span className={`inline-flex items-center gap-2 text-[16px] tracking-[-0.02em] ${health === "good" ? "text-emerald-700" : health === "bad" ? "text-rose-700" : "text-amber-700"}`}>
              {health === "good" ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}
              {health === "good" ? "Operational" : health === "bad" ? "Unavailable" : "Checking"}
            </span>
          }
          detail="Live readiness probe"
          tone={health === "good" ? "emerald" : "amber"}
          icon={<Activity size={18} />}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.65fr_1fr]">
        <div className="rounded-[22px] border border-[#e1e8e4] bg-white p-5 shadow-[0_10px_34px_rgba(28,55,43,0.045)] sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#809087]">Operational modules</p>
              <h2 className="mt-1 text-[20px] font-black tracking-[-0.025em] text-[#193027]">Run the platform from one place</h2>
              <p className="mt-1 text-[11px] text-[#77867e]">Fast access to the control areas used most often.</p>
            </div>
            <span className="hidden rounded-full bg-[#f3f7f5] px-3 py-1.5 text-[9px] font-black uppercase tracking-[0.08em] text-[#62746b] sm:inline-flex">
              {modules.length} modules
            </span>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {modules.map(({ title, copy, href, icon: Icon, accent }) => (
              <Link
                key={title}
                href={href}
                className={`group relative overflow-hidden rounded-2xl border border-[#e3eae6] bg-gradient-to-br ${accent} p-4 transition duration-200 hover:-translate-y-0.5 hover:border-[#cadbd4] hover:shadow-[0_12px_28px_rgba(25,55,42,0.08)]`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="grid h-10 w-10 place-items-center rounded-xl border border-white bg-white/85 text-[#1b514b] shadow-sm">
                    <Icon size={18} />
                  </div>
                  <ArrowRight size={15} className="mt-1 text-[#a2afa8] transition group-hover:translate-x-0.5 group-hover:text-[#1b514b]" />
                </div>
                <p className="mt-4 text-[13px] font-black text-[#1e342b]">{title}</p>
                <p className="mt-1.5 min-h-9 text-[10px] leading-[18px] text-[#74837b]">{copy}</p>
              </Link>
            ))}
          </div>
        </div>

        <div className="rounded-[22px] border border-[#e1e8e4] bg-white p-5 shadow-[0_10px_34px_rgba(28,55,43,0.045)] sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#809087]">Recent activity</p>
              <h2 className="mt-1 text-[20px] font-black tracking-[-0.025em] text-[#193027]">Control-plane events</h2>
            </div>
            <Link href="/audit" className="inline-flex items-center gap-1 text-[10px] font-black text-[#1b514b] hover:underline">
              View all <ArrowRight size={12} />
            </Link>
          </div>

          <div className="mt-5">
            {audit.length ? (
              <div className="space-y-1">
                {audit.slice(0, 6).map((row, index) => (
                  <div key={row.id} className="group relative flex gap-3 rounded-xl px-1 py-3">
                    <div className="relative flex w-8 shrink-0 justify-center">
                      <span className="z-10 mt-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#2c766d] shadow-[0_0_0_2px_#dfece8]" />
                      {index < Math.min(audit.length, 6) - 1 ? <span className="absolute bottom-[-10px] top-4 w-px bg-[#e3eae6]" /> : null}
                    </div>
                    <div className="min-w-0 flex-1 border-b border-[#edf1ef] pb-3 group-last:border-0 group-last:pb-0">
                      <div className="flex items-start justify-between gap-3">
                        <p className="truncate text-[11px] font-black text-[#263b32]">{row.action}</p>
                        <span className="shrink-0 text-[8px] font-semibold text-[#96a39c]">{new Date(row.created_at).toLocaleDateString()}</span>
                      </div>
                      <p className="mt-1 truncate text-[9px] text-[#7c8a83]">{row.resource_type || "control-plane resource"}</p>
                      <p className="mt-1 flex items-center gap-1 text-[8px] text-[#9aa69f]"><Clock3 size={9} /> {new Date(row.created_at).toLocaleTimeString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-[#dce5e0] bg-[#f8faf9] p-6 text-center">
                <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-white text-[#2c6d65] shadow-sm"><Activity size={18} /></div>
                <p className="mt-3 text-[12px] font-black text-[#294037]">No recent activity yet</p>
                <p className="mx-auto mt-1 max-w-xs text-[10px] leading-5 text-[#7d8b84]">Infrastructure changes and security events will appear here as you use the platform.</p>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.15fr_1fr_1fr]">
        <div className="rounded-[22px] border border-[#dfe8e3] bg-[linear-gradient(145deg,#f8fbf9,#ffffff)] p-5 shadow-[0_8px_28px_rgba(28,55,43,0.035)] sm:p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#809087]">Platform readiness</p>
              <h3 className="mt-1 text-[17px] font-black tracking-[-0.02em] text-[#1d342b]">Domain onboarding</h3>
            </div>
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#edf5f2] text-[#1b5a52]"><Globe2 size={19} /></div>
          </div>
          <div className="mt-5 flex items-end justify-between gap-4">
            <div>
              <p className="text-[30px] font-black leading-none tracking-[-0.04em] text-[#193027]">{loading ? "—" : `${verificationProgress}%`}</p>
              <p className="mt-1 text-[10px] text-[#7a8981]">Ownership verified</p>
            </div>
            <p className="text-right text-[9px] font-bold text-[#84928b]">DNS ready {readinessProgress}%</p>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#e8eeeb]">
            <div className="h-full rounded-full bg-[linear-gradient(90deg,#2d746b,#75a79e)] transition-[width] duration-700" style={{ width: `${verificationProgress}%` }} />
          </div>
        </div>

        <div className="rounded-[22px] border border-[#dfe8e3] bg-white p-5 shadow-[0_8px_28px_rgba(28,55,43,0.035)] sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#809087]">Security posture</p>
              <h3 className="mt-1 text-[17px] font-black tracking-[-0.02em] text-[#1d342b]">Privileged access</h3>
            </div>
            <div className={`grid h-11 w-11 place-items-center rounded-xl ${user?.mfa_enabled ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}><ShieldCheck size={19} /></div>
          </div>
          <div className="mt-5 flex items-center justify-between gap-4">
            <StatusBadge state={user?.mfa_enabled ? "good" : "warn"}>{user?.mfa_enabled ? "MFA enabled" : "MFA recommended"}</StatusBadge>
            <Link href="/security" className="inline-flex items-center gap-1 text-[10px] font-black text-[#1b514b] hover:underline">Review <ArrowRight size={12} /></Link>
          </div>
          <p className="mt-3 text-[10px] leading-5 text-[#7c8a83]">MFA and session controls protect administrator access to mail, DNS and customer infrastructure.</p>
        </div>

        <div className="rounded-[22px] border border-[#d8e4df] bg-[#173f3b] p-5 text-white shadow-[0_12px_34px_rgba(18,58,56,0.13)] sm:p-6">
          <p className="text-[10px] font-black uppercase tracking-[0.14em] text-[#a9c2bb]">Recommended next step</p>
          <h3 className="mt-2 text-[17px] font-black tracking-[-0.02em]">{nextAction.title}</h3>
          <p className="mt-2 min-h-10 text-[10px] leading-5 text-[#c1d1cc]">{nextAction.copy}</p>
          <Link href={nextAction.href} className="mt-4 inline-flex min-h-9 items-center gap-2 rounded-lg bg-[#d8c56a] px-3.5 text-[10px] font-black text-[#173c36] transition hover:bg-[#e1d07a]">
            {nextAction.label} <ArrowRight size={12} />
          </Link>
        </div>
      </section>
    </div>
  );
}
