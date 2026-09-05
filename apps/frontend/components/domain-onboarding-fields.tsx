"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Globe2, Loader2, RefreshCw, Server, ShieldCheck } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Plan = {
  code: string;
  name: string;
  currency: string;
  monthly_price_minor: number;
  included_mailboxes: number;
  included_domains: number;
  included_storage_mb: number;
  max_api_keys: number;
};

type PackageUsage = {
  mailboxes: number;
  domains: number;
  allocated_storage_bytes: number;
  api_keys: number;
};

type Inspection = {
  ascii_name: string;
  unicode_name: string;
  claim_status: "available" | "this_organization" | "another_organization";
  requested_dns_mode: "platform" | "external";
  lookup_status: "found" | "no_nameservers" | "nxdomain" | "timeout" | "resolver_error";
  lookup_detail?: string | null;
  current_nameservers: string[];
  current_provider?: string | null;
  platform_nameservers: string[];
  platform_nameservers_configured: boolean;
  already_on_platform_nameservers: boolean;
  nameserver_change_required: boolean;
  next_step: string;
  package?: { plan_code?: string; plan_name?: string; status?: string } | null;
  package_usage: PackageUsage;
  domain_capacity: { allowed: boolean; reason?: string | null; used: number; limit?: number | null; remaining?: number | null };
};

type Props = {
  tenantId: string;
  isPlatformOwner: boolean;
};

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refreshed = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refreshed.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

function money(plan: Plan) {
  return `${plan.currency === "LSL" ? "M" : plan.currency} ${(plan.monthly_price_minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/month`;
}

function validDomainCandidate(value: string) {
  const name = value.trim();
  return Boolean(name && !/\s/.test(name) && !name.includes("://") && !name.includes("/") && !name.includes("@") && name.includes("."));
}

function planFitsExistingUsage(plan: Plan, usage?: PackageUsage | null) {
  if (!usage) return true;
  return (
    usage.mailboxes <= plan.included_mailboxes
    && usage.domains + 1 <= plan.included_domains
    && usage.allocated_storage_bytes <= plan.included_storage_mb * 1024 * 1024
    && usage.api_keys <= plan.max_api_keys
  );
}

export function DomainOnboardingFields({ tenantId, isPlatformOwner }: Props) {
  const [name, setName] = useState("");
  const [dnsMode, setDnsMode] = useState<"platform" | "external">("platform");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentPlanCode, setCurrentPlanCode] = useState("");
  const [selectedPlanCode, setSelectedPlanCode] = useState("");
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [inspectError, setInspectError] = useState("");
  const inspectSequence = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function loadBillingContext() {
      if (!tenantId) return;
      try {
        const [plansResponse, summaryResponse] = await Promise.all([
          api("/billing/plans"),
          api(`/tenants/${tenantId}/billing/summary`),
        ]);
        if (plansResponse.ok) {
          const data = await plansResponse.json();
          if (!cancelled) setPlans(data.items || []);
        }
        if (summaryResponse.ok) {
          const summary = await summaryResponse.json();
          const code = String(summary.subscription?.plan_code || "");
          if (!cancelled) {
            setCurrentPlanCode(code);
            setSelectedPlanCode(code);
          }
        }
      } catch {
        // Final backend entitlement enforcement remains authoritative.
      }
    }
    void loadBillingContext();
    return () => { cancelled = true; };
  }, [tenantId]);

  async function inspect(candidate = name, mode = dnsMode) {
    const cleaned = candidate.trim();
    if (!tenantId || !validDomainCandidate(cleaned)) return;
    const sequence = ++inspectSequence.current;
    setInspecting(true);
    setInspectError("");
    try {
      const response = await api(`/tenants/${tenantId}/domain-onboarding/inspect`, {
        method: "POST",
        body: JSON.stringify({ name: cleaned, dns_mode: mode }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(String(body.detail || "Unable to inspect the domain"));
      }
      const data: Inspection = await response.json();
      if (sequence !== inspectSequence.current) return;
      setInspection(data);
      const code = String(data.package?.plan_code || currentPlanCode || "");
      setCurrentPlanCode(code);
      setSelectedPlanCode((existing) => existing || code);
    } catch (reason) {
      if (sequence !== inspectSequence.current) return;
      setInspection(null);
      setInspectError(reason instanceof Error ? reason.message : "Unable to inspect the domain");
    } finally {
      if (sequence === inspectSequence.current) setInspecting(false);
    }
  }

  const selectedPlan = useMemo(() => plans.find((plan) => plan.code === selectedPlanCode), [plans, selectedPlanCode]);
  const selectedCapacity = inspection && selectedPlan
    ? {
        used: inspection.domain_capacity.used,
        limit: selectedPlan.included_domains,
        availableNow: Math.max(0, selectedPlan.included_domains - inspection.domain_capacity.used),
      }
    : null;
  const packageChange = Boolean(isPlatformOwner && selectedPlanCode && selectedPlanCode !== currentPlanCode);
  const selectedPlanFitsUsage = selectedPlan
    ? planFitsExistingUsage(selectedPlan, inspection?.package_usage)
    : Boolean(inspection?.domain_capacity.allowed);
  const selectedPlanAllowsDomain = Boolean(
    inspection
    && selectedPlanFitsUsage
    && (packageChange ? isPlatformOwner : inspection.domain_capacity.allowed)
  );
  const claimAvailable = inspection?.claim_status === "available";

  return (
    <>
      <input type="hidden" name="current_plan_code" value={currentPlanCode}/>
      <input type="hidden" name="onboarding_inspected" value={inspection ? "true" : "false"}/>
      <input type="hidden" name="selected_plan_allows_domain" value={selectedPlanAllowsDomain ? "true" : "false"}/>
      <input type="hidden" name="domain_claim_available" value={claimAvailable ? "true" : "false"}/>

      <div className="mt-5 form-field">
        <label className="form-label" htmlFor="domain-name"><span>Domain name</span><span className="form-required">Required</span></label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id="domain-name"
            name="name"
            className="input flex-1"
            placeholder="example.co.ls"
            required
            autoFocus
            maxLength={320}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            inputMode="url"
            value={name}
            onChange={(event) => {
              inspectSequence.current += 1;
              setInspecting(false);
              setName(event.target.value);
              setInspection(null);
              setInspectError("");
            }}
            onBlur={() => { if (validDomainCandidate(name)) void inspect(); }}
            aria-describedby="domain-name-help"
          />
          <button type="button" className="btn-secondary shrink-0" disabled={!validDomainCandidate(name) || inspecting} onClick={() => void inspect()}>
            {inspecting ? <Loader2 size={14} className="animate-spin"/> : <RefreshCw size={14}/>}Check domain
          </button>
        </div>
        <p id="domain-name-help" className="form-helper">Enter only the registered domain. We inspect its live public nameservers before onboarding it.</p>
      </div>

      <div className="form-field">
        <label className="form-label" htmlFor="dns-mode">DNS hosting intent</label>
        <select
          id="dns-mode"
          name="dns_mode"
          className="input"
          value={dnsMode}
          onChange={(event) => {
            const next = event.target.value as "platform" | "external";
            inspectSequence.current += 1;
            setInspecting(false);
            setDnsMode(next);
            setInspection(null);
            if (validDomainCandidate(name)) void inspect(name, next);
          }}
          aria-describedby="dns-mode-help"
        >
          <option value="platform">Host authoritative DNS on Mailbox DNS / PowerDNS</option>
          <option value="external">Keep the current external DNS provider</option>
        </select>
        <div id="dns-mode-help" className="mt-2 grid gap-2 sm:grid-cols-2">
          <div className={`rounded-xl border p-3 text-[10px] leading-4 ${dnsMode === "platform" ? "border-[#87a69d] bg-[#f2f8f6]" : "border-[#e1e7e3] bg-[#fafcfb]"}`}>
            <div className="flex items-center gap-2 font-black text-[#294a40]"><Server size={13}/>Mailbox DNS / PowerDNS</div>
            <p className="mt-1 text-[#687970]">We become authoritative DNS. After verification and zone preparation, change the registrar nameservers to ours. DNS and email records can then be automated here.</p>
          </div>
          <div className={`rounded-xl border p-3 text-[10px] leading-4 ${dnsMode === "external" ? "border-[#87a69d] bg-[#f2f8f6]" : "border-[#e1e7e3] bg-[#fafcfb]"}`}>
            <div className="flex items-center gap-2 font-black text-[#294a40]"><Globe2 size={13}/>External DNS</div>
            <p className="mt-1 text-[#687970]">Keep Zeecom, Cloudflare or another provider authoritative. Email may still be hosted here, but TXT/MX/SPF/DKIM/DMARC changes must be published at that provider.</p>
          </div>
        </div>
      </div>

      {inspectError ? <div className="form-field rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] font-semibold text-red-700"><div className="flex gap-2"><AlertTriangle size={14} className="mt-0.5 shrink-0"/><span>{inspectError}</span></div></div> : null}

      {inspection ? <div className="form-field rounded-xl border border-[#dce5e0] bg-[#f8fbf9] p-3" aria-live="polite">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-black text-[#263a31]"><ShieldCheck size={14}/>Current DNS delegation</div>
            <p className="mt-1 text-[10px] text-[#718078]">Live public lookup for <b>{inspection.ascii_name}</b></p>
          </div>
          {inspection.lookup_status === "found" ? <span className="status-badge status-verified">Detected</span> : <span className="status-badge status-pending">Check needed</span>}
        </div>

        {inspection.current_nameservers.length ? <div className="mt-3">
          <p className="text-[10px] font-black text-[#52635a]">Current provider: {inspection.current_provider || "External DNS provider"}</p>
          <div className="mt-2 grid gap-1.5">
            {inspection.current_nameservers.map((server) => <code key={server} className="rounded-lg border bg-white px-2.5 py-2 text-[10px] text-[#263a31]">{server}</code>)}
          </div>
        </div> : <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800">{inspection.lookup_detail || "No current nameservers were discovered."}</p>}

        {dnsMode === "platform" ? (
          inspection.platform_nameservers_configured ? <div className="mt-3 rounded-lg border border-[#cddbd5] bg-white p-3">
            <p className="text-[10px] font-black text-[#294a40]">Mailbox DNS target nameservers</p>
            <div className="mt-2 grid gap-1.5">
              {inspection.platform_nameservers.map((server) => <code key={server} className="rounded-md bg-[#f3f6f4] px-2 py-1.5 text-[10px]">{server}</code>)}
            </div>
            <p className={`mt-2 text-[10px] font-bold ${inspection.nameserver_change_required ? "text-amber-700" : "text-emerald-700"}`}>
              {inspection.nameserver_change_required ? "Nameserver change will be required after verification." : "This domain already uses the platform nameservers."}
            </p>
          </div> : <div className="mt-3 flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-[10px] leading-4 text-amber-900">
            <AlertTriangle size={14} className="mt-0.5 shrink-0"/>
            <span><b>Do not change the registrar nameservers yet.</b> Real public Mailbox DNS nameserver hostnames are not configured on this production installation. Keep Zeecom/current DNS active while ownership is verified.</span>
          </div>
        ) : <div className="mt-3 flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[10px] leading-4 text-emerald-800"><CheckCircle2 size={13} className="mt-0.5 shrink-0"/><span>No registrar nameserver change is required in External DNS mode.</span></div>}

        <p className="mt-3 text-[10px] leading-4 text-[#607168]"><b>Next:</b> {inspection.next_step}</p>
        {inspection.claim_status !== "available" ? <p className="mt-2 text-[10px] font-bold text-red-700">This domain is already claimed {inspection.claim_status === "this_organization" ? "by this organization" : "by another organization"}. It cannot be added again.</p> : null}
      </div> : null}

      <div className="form-field">
        <label className="form-label" htmlFor="domain-package"><span>Hosting package</span><span className="font-normal text-[#89958e]">Organization subscription</span></label>
        {isPlatformOwner ? <select id="domain-package" name="plan_code" className="input" value={selectedPlanCode} onChange={(event) => setSelectedPlanCode(event.target.value)} required>
          <option value="">Select package</option>
          {plans.map((plan) => <option key={plan.code} value={plan.code} disabled={Boolean(inspection && !planFitsExistingUsage(plan, inspection.package_usage))}>{plan.name} · {money(plan)} · {plan.included_domains} domains · {plan.included_mailboxes} mailboxes</option>)}
        </select> : <input id="domain-package" className="input" value={selectedPlan?.name || inspection?.package?.plan_name || "Managed by billing administrator"} readOnly/>}
        <p className="form-helper">Packages apply to the whole organization, not to one domain. Domain creation consumes one domain slot from the organization package.</p>
        {selectedPlan ? <div className="mt-2 rounded-lg border border-[#e1e7e3] bg-[#fafcfb] px-3 py-2 text-[10px] leading-4 text-[#607168]">
          <b>{selectedPlan.name}</b>: {selectedPlan.included_domains} domains, {selectedPlan.included_mailboxes} mailboxes, {(selectedPlan.included_storage_mb / 1000).toLocaleString()} GB allocated storage.
          {selectedCapacity ? <> Current domain use: <b>{selectedCapacity.used}/{selectedCapacity.limit}</b>; {selectedCapacity.availableNow} domain slot{selectedCapacity.availableNow === 1 ? "" : "s"} available now. This domain will use one.</> : null}
          {packageChange ? <span className="mt-1 block font-bold text-amber-700">This will administratively change the organization package before the domain is created.</span> : null}
          {inspection && !selectedPlanAllowsDomain ? <span className="mt-1 block font-bold text-red-700">This package cannot currently add the domain. Check package capacity and subscription status, or choose a larger active package.</span> : null}
        </div> : inspection && !inspection.package ? <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-semibold text-amber-800">No active package is assigned. A package is required before production can create another domain.</div> : null}
      </div>

      <div className="form-field">
        <label className="form-check-row" htmlFor="mail-enabled">
          <input id="mail-enabled" type="checkbox" name="mail_enabled" defaultChecked/>
          <span><span className="block text-[12px] font-black text-[#263a31]">Enable email hosting for this domain</span><span className="mt-1 block text-[10px] leading-4 text-[#718078]">Allows mailbox, SMTP/IMAP and mail-authentication onboarding after domain ownership is verified.</span></span>
        </label>
      </div>

      <div className="form-field">
        <label className="form-label" htmlFor="domain-notes">Internal notes <span className="font-normal text-[#89958e]">Optional</span></label>
        <textarea id="domain-notes" name="notes" className="input" placeholder="Registrar, migration or customer notes…" maxLength={4000} aria-describedby="domain-notes-help"/>
        <p id="domain-notes-help" className="form-helper">Visible to administrators; maximum 4,000 characters.</p>
      </div>
    </>
  );
}
