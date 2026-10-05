"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ControlCentreOverview } from "@/components/control-centre-overview";
import { ControlCentreExtras, type ControlCentreAudit } from "@/components/control-centre-extras";
import { apiFetch, PLATFORM_API_URL } from "@/lib/platform-api";

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

type Health = "good" | "bad" | "warn";

async function api(path: string) {
  return apiFetch(path, { cache: "no-store" });
}

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [tenantCount, setTenantCount] = useState(0);
  const [domainCount, setDomainCount] = useState(0);
  const [verifiedCount, setVerifiedCount] = useState(0);
  const [dnsReady, setDnsReady] = useState(0);
  const [health, setHealth] = useState<Health>("warn");
  const [audit, setAudit] = useState<ControlCentreAudit[]>([]);
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
          const healthResponse = await fetch(`${PLATFORM_API_URL.replace(/\/api\/v1$/, "")}/health/ready`, {
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

  const firstName = user?.full_name?.trim().split(/\s+/)[0] || (user?.is_platform_owner ? "Platform Owner" : "there");

  const nextAction = domainCount === 0
    ? { title: "Add your first domain", copy: "Add a domain, verify ownership and connect it to Ithute services.", href: "/domains", label: "Add domain" }
    : verifiedCount < domainCount
      ? { title: "Finish domain verification", copy: `${domainCount - verifiedCount} domain${domainCount - verifiedCount === 1 ? "" : "s"} still need ownership verification.`, href: "/domains", label: "Review domains" }
      : dnsReady < domainCount
        ? { title: "Complete DNS onboarding", copy: "Verified domains can now be moved onto authoritative Ithute DNS where required.", href: "/dns", label: "Configure DNS" }
        : { title: "Expand your Ithute services", copy: "Core domain onboarding is healthy. Continue with hosting, mail, API access or organisation controls.", href: "/hosting", label: "Open hosting" };

  return (
    <div className="space-y-5 pb-8">
      <ControlCentreOverview
        health={health}
        firstName={firstName}
        loading={loading}
        tenantCount={tenantCount}
        domainCount={domainCount}
        verifiedCount={verifiedCount}
        dnsReady={dnsReady}
        verificationProgress={verificationProgress}
        nextAction={nextAction}
      />
      <ControlCentreExtras audit={audit} loading={loading} />
    </div>
  );
}
