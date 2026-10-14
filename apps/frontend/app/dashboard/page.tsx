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

async function api(path: string, signal?: AbortSignal) {
  return apiFetch(path, { cache: "no-store", signal });
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
  const [domainsLoading, setDomainsLoading] = useState(true);
  const [auditLoading, setAuditLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    void (async () => {
      try {
        const meResponse = await api("/auth/me", signal);
        if (signal.aborted) return;
        if (!meResponse.ok) {
          router.replace("/login");
          return;
        }

        const me: User = await meResponse.json();
        if (signal.aborted) return;
        setUser(me);

        let contexts: Membership[] = [];
        if (me.is_platform_owner) {
          const tenantResponse = await api("/tenants", signal);
          const data = tenantResponse.ok ? await tenantResponse.json() : [];
          contexts = data.map((item: { id: string; name: string; status: string }) => ({
            tenant_id: item.id,
            tenant_name: item.name,
            status: item.status,
          }));
        } else {
          const membershipResponse = await api("/me/memberships", signal);
          contexts = membershipResponse.ok ? await membershipResponse.json() : [];
        }

        if (signal.aborted) return;
        const activeContexts = contexts.filter((context) => context.status === "active");
        if (signal.aborted) return;
        setTenantCount(activeContexts.length);

        const auditPath = me.is_platform_owner
          ? "/audit/platform?limit=8"
          : activeContexts[0]
            ? `/tenants/${activeContexts[0].tenant_id}/audit?limit=8`
            : null;

        // Start independent tasks together. Domain aggregation is bounded to
        // five active requests and never blocks audit or readiness indicators.
        await Promise.allSettled([
          (async () => {
            try {
              const contextsToLoad = activeContexts.slice(0, 20);
              const domains: Domain[] = [];
              for (let offset = 0; offset < contextsToLoad.length; offset += 5) {
                if (signal.aborted) return;
                const batch = contextsToLoad.slice(offset, offset + 5);
                const results = await Promise.allSettled(
                  batch.map(async (context): Promise<Domain[]> => {
                    const response = await api(`/tenants/${context.tenant_id}/domains`, signal);
                    if (!response.ok || signal.aborted) return [];
                    const body: { items?: Domain[] } = await response.json();
                    return signal.aborted ? [] : Array.isArray(body.items) ? body.items : [];
                  }),
                );
                for (const result of results) {
                  if (result.status === "fulfilled") domains.push(...result.value);
                }
              }
              if (signal.aborted) return;
              setDomainCount(domains.length);
              setVerifiedCount(domains.filter((domain) => Boolean(domain.ownership_verified_at)).length);
              setDnsReady(domains.filter((domain) =>
                domain.status === "verified" &&
                domain.dns_mode === "platform" &&
                Boolean(domain.ownership_verified_at),
              ).length);
            } finally {
              if (!signal.aborted) setDomainsLoading(false);
            }
          })(),
          (async () => {
            try {
              if (!auditPath) return;
              const response = await api(auditPath, signal);
              if (response.ok) {
                const auditData = await response.json();
                if (!signal.aborted) setAudit(auditData);
              }
            } finally {
              if (!signal.aborted) setAuditLoading(false);
            }
          })(),
          (async () => {
            try {
              const response = await fetch(`${PLATFORM_API_URL.replace(/\/api\/v1$/, "")}/health/ready`, {
                cache: "no-store",
                signal,
              });
              if (!signal.aborted) setHealth(response.ok ? "good" : "bad");
            } catch {
              if (!signal.aborted) setHealth("bad");
            }
          })(),
        ]);
      } catch (error) {
        // A broken optional service should not trap the dashboard in a spinner.
        if (!signal.aborted) console.error("Ithute dashboard initialization failed", error);
      } finally {
        if (!signal.aborted) {
          setDomainsLoading(false);
          setAuditLoading(false);
        }
      }
    })();
    return () => controller.abort();
  }, [router]);

  const verificationProgress = useMemo(
    () => (domainCount ? Math.round((verifiedCount / domainCount) * 100) : 0),
    [domainCount, verifiedCount],
  );

  const firstName = user?.full_name?.trim().split(/\s+/)[0] || (user?.is_platform_owner ? "Platform Owner" : "there");

  const nextAction = domainsLoading
    ? { title: "Reviewing your domains", copy: "Checking domain readiness across your organisations.", href: "/domains", label: "Open domains" }
    : domainCount === 0
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
        loading={domainsLoading}
        tenantCount={tenantCount}
        domainCount={domainCount}
        verifiedCount={verifiedCount}
        dnsReady={dnsReady}
        verificationProgress={verificationProgress}
        nextAction={nextAction}
      />
      <ControlCentreExtras audit={audit} loading={auditLoading} />
    </div>
  );
}
