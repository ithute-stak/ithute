"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Copy,
  Database,
  Globe2,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { DomainOnboardingFields } from "@/components/domain-onboarding-fields";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; role: string; status: string };
type Domain = {
  id: string;
  ascii_name: string;
  unicode_name: string;
  status: "pending_verification" | "verified" | "suspended" | "archived";
  dns_mode: "external" | "platform";
  mail_enabled: boolean;
  notes?: string | null;
  verification_method: "txt" | "nameserver";
  verification_record_name: string;
  verification_token_hint: string;
  ownership_verified_at?: string | null;
};
type Challenge = { domain_id: string; record_name: string; verification_value: string };

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

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return String(body.detail || fallback);
}

function badge(status: Domain["status"]) {
  if (status === "verified") return "status-verified";
  if (status === "suspended") return "status-suspended";
  if (status === "archived") return "status-archived";
  return "status-pending";
}

export default function DomainsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [domains, setDomains] = useState<Domain[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [challengeToken, setChallengeToken] = useState("");
  const [releaseTarget, setReleaseTarget] = useState<Domain | null>(null);
  const [releaseText, setReleaseText] = useState("");
  const [releasing, setReleasing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || selected?.role === "tenant_admin" || selected?.role === "dns_admin");

  useEffect(() => {
    async function bootstrap() {
      try {
        const meResponse = await api("/auth/me");
        if (meResponse.status === 401) {
          router.replace("/login");
          return;
        }
        if (!meResponse.ok) throw new Error("Unable to load account");
        const current: Me = await meResponse.json();
        setMe(current);

        let rows: Membership[] = [];
        if (current.is_platform_owner) {
          const tenantsResponse = await api("/tenants");
          if (!tenantsResponse.ok) throw new Error("Unable to load organizations");
          const tenants = await tenantsResponse.json();
          rows = tenants.map((tenant: { id: string; name: string; status: string }) => ({
            tenant_id: tenant.id,
            tenant_name: tenant.name,
            role: "platform_owner",
            status: tenant.status,
          }));
        } else {
          const membershipsResponse = await api("/me/memberships");
          if (!membershipsResponse.ok) throw new Error("Unable to load organizations");
          rows = await membershipsResponse.json();
        }
        const active = rows.filter((row) => row.status === "active");
        setContexts(active);
        const remembered = localStorage.getItem("mailbox_dns_tenant");
        setTenantId(active.find((row) => row.tenant_id === remembered)?.tenant_id || active[0]?.tenant_id || "");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Unable to initialize domain portfolio");
      } finally {
        setLoading(false);
      }
    }
    void bootstrap();
  }, [router]);

  useEffect(() => {
    if (!tenantId) return;
    localStorage.setItem("mailbox_dns_tenant", tenantId);
    void loadDomains();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  async function loadDomains() {
    if (!tenantId) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      const response = await api(`/tenants/${tenantId}/domains?${params.toString()}`);
      if (!response.ok) throw new Error(await detail(response, "Unable to load domains"));
      const data = await response.json();
      setDomains(data.items || []);
      setTotal(data.total || 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load domains");
    } finally {
      setLoading(false);
    }
  }

  async function addDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId || adding) return;
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    const notes = String(form.get("notes") || "").trim();
    const selectedPlanCode = String(form.get("plan_code") || "").trim();
    const currentPlanCode = String(form.get("current_plan_code") || "").trim();
    const inspected = form.get("onboarding_inspected") === "true";
    const claimAvailable = form.get("domain_claim_available") === "true";
    const selectedPlanAllowsDomain = form.get("selected_plan_allows_domain") === "true";

    if (!name) {
      setError("Domain name is required.");
      return;
    }
    if (/\s/.test(name) || name.includes("://") || name.includes("/") || name.includes("@")) {
      setError("Enter only the domain name, for example example.co.ls — no https://, path, email address or spaces.");
      return;
    }
    if (!inspected) {
      setError("Check the domain first so its current public nameservers and onboarding requirements can be confirmed.");
      return;
    }
    if (!claimAvailable) {
      setError("This domain is already claimed on Mailbox DNS. Resolve or release the existing claim before changing a package or adding it again.");
      return;
    }
    if (!selectedPlanAllowsDomain) {
      setError("The selected/current package cannot accommodate this domain. Choose a package with enough capacity before continuing.");
      return;
    }
    if (me?.is_platform_owner && !selectedPlanCode) {
      setError("Select the organization hosting package before adding the domain.");
      return;
    }

    setAdding(true);
    try {
      let packageChanged = false;
      if (me?.is_platform_owner && selectedPlanCode && selectedPlanCode !== currentPlanCode) {
        const subscriptionResponse = await api(`/tenants/${tenantId}/billing/subscription`, {
          method: "PUT",
          body: JSON.stringify({ plan_code: selectedPlanCode, status: "active", period_days: 30 }),
        });
        if (!subscriptionResponse.ok) throw new Error(await detail(subscriptionResponse, "Unable to assign the selected hosting package"));
        packageChanged = true;
      }

      const response = await api(`/tenants/${tenantId}/domains`, {
        method: "POST",
        body: JSON.stringify({
          name,
          dns_mode: String(form.get("dns_mode") || "platform"),
          mail_enabled: form.get("mail_enabled") === "on",
          notes: notes || null,
        }),
      });
      if (!response.ok) throw new Error(await detail(response, "Unable to add domain"));
      const created: Domain & { verification_value?: string | null } = await response.json();
      if (created.verification_method === "txt" && created.verification_value) {
        setChallenge({
          domain_id: created.id,
          record_name: created.verification_record_name,
          verification_value: created.verification_value,
        });
        setChallengeToken(created.verification_value.split("=", 2)[1] || "");
      } else {
        setChallenge(null);
        setChallengeToken("");
      }
      setShowAdd(false);
      setMessage(
        created.verification_method === "nameserver"
          ? `${created.ascii_name} added${packageChanged ? ` under the ${selectedPlanCode} package` : ""}. No TXT token is required. Prepare DNS and records first, then delegate the registrar to both Ithute nameservers and verify after propagation.`
          : `${created.ascii_name} added${packageChanged ? ` under the ${selectedPlanCode} package` : ""}. Existing/external DNS requires the one-time TXT ownership record before cutover.`,
      );
      await loadDomains();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add domain");
    } finally {
      setAdding(false);
    }
  }

  async function regenerate(domain: Domain) {
    setError("");
    const response = await api(`/tenants/${tenantId}/domains/${domain.id}/challenge`, { method: "POST" });
    if (!response.ok) {
      setError(await detail(response, "Could not regenerate verification challenge"));
      return;
    }
    const data = await response.json();
    setChallenge(data);
    setChallengeToken(data.verification_value.split("=", 2)[1] || "");
    setMessage("New one-time TXT challenge generated; the previous challenge is invalid.");
    await loadDomains();
  }

  async function verify(domain: Domain) {
    setError("");
    const tokenIsCurrent = Boolean(challengeToken && challenge?.domain_id === domain.id);
    const response = await api(`/tenants/${tenantId}/domains/${domain.id}/verify`, {
      method: "POST",
      body: JSON.stringify(tokenIsCurrent ? { token: challengeToken } : {}),
    });
    if (!response.ok) {
      setError(await detail(response, "Verification request failed"));
      return;
    }
    const data = await response.json();
    if (data.verified) {
      setChallenge(null);
      setChallengeToken("");
    }
    setMessage(
      data.verified
        ? `${domain.ascii_name} ownership verified. Reconcile its DNS zone to activate the verified DNS/mail lifecycle.`
        : domain.verification_method === "nameserver"
          ? "Ithute nameserver delegation is not complete yet. Make sure both ns1.ithute.co.ls and ns2.ithute.co.ls are set at the registrar, wait for propagation, then retry."
          : "TXT record not found or does not match the active challenge yet. Keep the current external DNS active and allow time for TXT propagation.",
    );
    await loadDomains();
  }

  async function archive(domain: Domain) {
    if (!window.confirm(`Archive ${domain.ascii_name}? The domain will become read-only until the platform owner permanently releases it.`)) return;
    setError("");
    const response = await api(`/tenants/${tenantId}/domains/${domain.id}`, { method: "DELETE" });
    if (!response.ok) {
      setError(await detail(response, "Unable to archive domain"));
      return;
    }
    setMessage(`${domain.ascii_name} archived. Platform owners can now permanently delete/release the claim.`);
    await loadDomains();
  }

  function openRelease(domain: Domain) {
    setReleaseTarget(domain);
    setReleaseText("");
    setError("");
    setMessage("");
  }

  async function releaseDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!releaseTarget || releasing) return;
    if (releaseText.trim().toLowerCase() !== releaseTarget.ascii_name.toLowerCase()) {
      setError(`Type ${releaseTarget.ascii_name} exactly to confirm permanent deletion.`);
      return;
    }
    setReleasing(true);
    setError("");
    try {
      const response = await api(`/tenants/${tenantId}/domains/${releaseTarget.id}/release`, { method: "DELETE" });
      if (!response.ok) throw new Error(await detail(response, "Unable to permanently delete domain claim"));
      const released = releaseTarget.ascii_name;
      setReleaseTarget(null);
      setReleaseText("");
      setChallenge((current) => current?.domain_id === releaseTarget.id ? null : current);
      setChallengeToken("");
      setMessage(`${released} permanently deleted and its global domain claim released.`);
      await loadDomains();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to permanently delete domain claim");
    } finally {
      setReleasing(false);
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage("Copied to clipboard.");
    } catch {
      setError("Clipboard access was blocked by the browser. Select and copy the value manually.");
    }
  }

  return (
    <ControlShell title="Domain portfolio" subtitle="Ownership, lifecycle and PowerDNS readiness" userEmail={me?.email}>
      <div className="space-y-4">
        <section className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[.12em] text-[#718078]"><Globe2 size={14}/>Phase 3 · Domain management</div>
              <h1 className="mt-2 text-2xl font-black tracking-tight text-[#21342a]">Domains under management</h1>
              <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[#718078]">Stage Platform DNS before registrar cutover. New registrar/reseller domains verify by Ithute nameserver delegation; existing DNS migrations verify by TXT before cutover.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="domain-organization">Organization</label>
              <select id="domain-organization" value={tenantId} onChange={(event) => setTenantId(event.target.value)} className="input min-w-[230px]" aria-label="Organization">
                <option value="">Select organization</option>
                {contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name} · {row.role.replaceAll("_", " ")}</option>)}
              </select>
              {canManage && tenantId ? <button type="button" onClick={() => setShowAdd(true)} className="btn-primary"><Plus size={15}/>Add domain</button> : null}
            </div>
          </div>
        </section>

        {!contexts.length && !loading ? <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] font-semibold text-amber-800">No active organization is available. Create or activate an organization before adding a domain.</div> : null}
        {error ? <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] font-semibold text-red-700"><AlertTriangle size={15} className="mt-0.5 shrink-0"/><span>{error}</span><button type="button" className="ml-auto" onClick={() => setError("")} aria-label="Dismiss error"><X size={15}/></button></div> : null}
        {message ? <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[12px] font-semibold text-emerald-700"><CheckCircle2 size={15} className="mt-0.5 shrink-0"/><span>{message}</span><button type="button" className="ml-auto" onClick={() => setMessage("")} aria-label="Dismiss message"><X size={15}/></button></div> : null}

        {challenge ? <section className="rounded-2xl border border-[#d8c56a] bg-[#fffdf3] p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#123a38] text-white"><ShieldCheck size={18}/></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black text-[#21342a]">TXT ownership verification</p>
              <p className="mt-1 text-[11px] text-[#718078]">Existing/external DNS was detected. Publish this one-time TXT record at the DNS provider currently serving the domain. Keep the existing nameservers in place while you stage or import all records needed for a safe cutover.</p>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {[["TXT host / name", challenge.record_name], ["TXT value", challenge.verification_value]].map(([label, value]) => <div key={label}>
                  <span className="label">{label}</span>
                  <div className="flex gap-2"><code className="min-w-0 flex-1 overflow-x-auto rounded-lg border bg-white px-3 py-2 text-[11px]">{value}</code><button type="button" onClick={() => void copy(value)} className="btn-secondary px-3" aria-label={`Copy ${label}`}><Copy size={14}/></button></div>
                </div>)}
              </div>
            </div>
          </div>
        </section> : null}

        <section className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm sm:p-5">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="text-sm font-black text-[#21342a]">Domain inventory</p><p className="text-[10px] text-[#819087]">{total} domain{total === 1 ? "" : "s"} in this organization</p></div>
            <form className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row" onSubmit={(event) => { event.preventDefault(); void loadDomains(); }} role="search">
              <label className="sr-only" htmlFor="domain-search">Search domains</label>
              <div className="relative min-w-0 sm:min-w-[260px]"><Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#89958e]"/><input id="domain-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by domain name" className="input pl-9" autoComplete="off" spellCheck={false}/></div>
              <button className="btn-secondary" type="submit" disabled={loading}>{loading ? <Loader2 size={14} className="animate-spin"/> : <Search size={14}/>}Search</button>
              <button className="btn-secondary px-3" type="button" onClick={() => void loadDomains()} disabled={loading} aria-label="Refresh domains" title="Refresh domains"><RefreshCw size={14} className={loading ? "animate-spin" : ""}/></button>
            </form>
          </div>

          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Domain</th><th>Status</th><th>DNS mode</th><th>Mail</th><th>Verification</th><th>Actions</th></tr></thead>
              <tbody>
                {domains.map((domain) => <tr key={domain.id}>
                  <td><div className="font-black text-[#21342a]">{domain.unicode_name}</div><div className="mt-1 font-mono text-[9px] text-[#89958e]">{domain.ascii_name}</div></td>
                  <td><span className={`status-badge ${badge(domain.status)}`}>{domain.status.replaceAll("_", " ")}</span></td>
                  <td><span className="font-bold capitalize">{domain.dns_mode}</span><div className="mt-1 text-[9px] text-[#89958e]">{domain.dns_mode === "platform" ? "PowerDNS" : "External DNS"}</div></td>
                  <td>{domain.mail_enabled ? <span className="font-bold text-emerald-700">Enabled</span> : <span className="text-[#89958e]">Disabled</span>}</td>
                  <td>
                    {domain.status === "archived" ? <span className="font-bold text-[#89958e]">Archived</span>
                      : domain.ownership_verified_at ? <span className="font-bold text-emerald-700">Ownership verified</span>
                      : domain.verification_method === "nameserver"
                        ? <div><div className="font-bold text-amber-700">Nameserver delegation required</div><div className="mt-1 text-[9px] text-[#89958e]">No TXT token required</div></div>
                        : <div><div className="font-bold text-amber-700">TXT required</div><div className="mt-1 text-[9px] text-[#89958e]">token …{domain.verification_token_hint}</div></div>}
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-2">
                      {canManage && domain.status !== "archived" && domain.dns_mode === "platform" ? <a href="/dns" className="btn-secondary !min-h-0 px-2.5 py-1.5 text-[10px]"><Database size={12}/>{domain.ownership_verified_at ? "Manage DNS" : "Prepare DNS"}</a> : null}
                      {canManage && domain.status !== "archived" && !domain.ownership_verified_at && domain.verification_method === "txt" ? <button type="button" onClick={() => void regenerate(domain)} className="btn-secondary !min-h-0 px-2.5 py-1.5 text-[10px]">New token</button> : null}
                      {canManage && domain.status !== "archived" && !domain.ownership_verified_at ? <button type="button" onClick={() => void verify(domain)} className="btn-primary !min-h-0 px-2.5 py-1.5 text-[10px]">Verify</button> : null}
                      {canManage && domain.status !== "archived" ? <button type="button" onClick={() => void archive(domain)} className="btn-danger !min-h-0 px-2.5 py-1.5 text-[10px]" title="Archive domain"><Archive size={12}/>Archive</button> : null}
                      {me?.is_platform_owner && domain.status === "archived" ? <button type="button" onClick={() => openRelease(domain)} className="btn-danger !min-h-0 px-2.5 py-1.5 text-[10px]" title="Permanently delete domain claim"><Trash2 size={12}/>Delete permanently</button> : null}
                    </div>
                  </td>
                </tr>)}
                {!domains.length && !loading ? <tr><td colSpan={6} className="py-10 text-center text-[#89958e]">No domains match this view. Add a domain or clear the search.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {showAdd ? <div className="fixed inset-0 z-[60] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !adding) setShowAdd(false); }}>
        <form onSubmit={addDomain} className="form-modal w-full max-w-3xl rounded-2xl bg-white p-5 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="add-domain-title">
          <div className="flex items-start justify-between gap-4">
            <div><p id="add-domain-title" className="text-lg font-black text-[#21342a]">Add domain</p><p className="mt-1 text-[11px] leading-5 text-[#718078]">Inspect current DNS, choose hosting, confirm package capacity, then stage Platform DNS before any registrar cutover.</p></div>
            <button type="button" onClick={() => setShowAdd(false)} disabled={adding} className="icon-button" aria-label="Close add-domain form"><X size={16}/></button>
          </div>

          <DomainOnboardingFields tenantId={tenantId} isPlatformOwner={Boolean(me?.is_platform_owner)}/>

          <div className="form-actions">
            <button type="button" onClick={() => setShowAdd(false)} disabled={adding} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={adding} className="btn-primary">{adding ? <><Loader2 size={14} className="animate-spin"/>Adding domain…</> : <><Plus size={14}/>Add domain</>}</button>
          </div>
        </form>
      </div> : null}

      {releaseTarget ? <div className="fixed inset-0 z-[70] grid place-items-center bg-black/55 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !releasing) setReleaseTarget(null); }}>
        <form onSubmit={releaseDomain} className="form-modal w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl" role="alertdialog" aria-modal="true" aria-labelledby="release-domain-title" aria-describedby="release-domain-description">
          <div className="flex items-start gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-red-50 text-red-700"><Trash2 size={19}/></div>
            <div className="min-w-0 flex-1"><p id="release-domain-title" className="text-lg font-black text-[#21342a]">Permanently delete domain claim</p><p id="release-domain-description" className="mt-1 text-[11px] leading-5 text-[#718078]">This removes <b>{releaseTarget.ascii_name}</b> from this platform and releases its global claim so it can be added again later. This action cannot be undone.</p></div>
          </div>
          <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] leading-5 text-red-800"><b>Platform owner only.</b> Clean abandoned claims can be removed; managed DNS/mail lifecycle resources must be deprovisioned first. Registrar or external-provider DNS records are never silently removed.</div>
          <div className="mt-5 form-field">
            <label className="form-label" htmlFor="release-confirmation"><span>Type the domain to confirm</span><span className="form-required">Required</span></label>
            <input id="release-confirmation" value={releaseText} onChange={(event) => setReleaseText(event.target.value)} className="input font-mono" placeholder={releaseTarget.ascii_name} autoComplete="off" autoCapitalize="none" spellCheck={false} required autoFocus aria-describedby="release-confirmation-help"/>
            <p id="release-confirmation-help" className="form-helper">Enter <b className="font-mono">{releaseTarget.ascii_name}</b> exactly.</p>
          </div>
          <div className="form-actions">
            <button type="button" className="btn-secondary" disabled={releasing} onClick={() => { setReleaseTarget(null); setReleaseText(""); }}>Cancel</button>
            <button type="submit" className="btn-danger" disabled={releasing || releaseText.trim().toLowerCase() !== releaseTarget.ascii_name.toLowerCase()}>{releasing ? <><Loader2 size={14} className="animate-spin"/>Deleting…</> : <><Trash2 size={14}/>Delete permanently</>}</button>
          </div>
        </form>
      </div> : null}
    </ControlShell>
  );
}