"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Database,
  Download,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { ConfirmDialog, EmptyState, PageHeader, StatusBadge, Toast } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; role: string; status: string };
type Domain = {
  id: string;
  ascii_name: string;
  unicode_name: string;
  status: "pending_verification" | "verified" | "suspended" | "archived";
  dns_mode: "external" | "platform";
  mail_enabled?: boolean;
  ownership_verified_at?: string | null;
};
type RecordRow = { content: string; disabled?: boolean };
type Rrset = { name: string; type: string; ttl: number; records: RecordRow[] };
type Zone = { name?: string; kind?: string; serial?: number; rrsets?: Rrset[] };
type RecordType = "A" | "AAAA" | "CNAME" | "MX" | "TXT" | "CAA" | "SRV";

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

function help(type: RecordType) {
  return {
    A: "IPv4 address, for example 192.0.2.10",
    AAAA: "IPv6 address, for example 2001:db8::10",
    CNAME: "Canonical target hostname. CNAME cannot be used at the zone apex.",
    MX: "Priority and mail server, for example 10 mail.example.com.",
    TXT: "Text value used by verification and email authentication. Include quotes only when the DNS value requires them.",
    CAA: "Flags, tag and value, for example 0 issue letsencrypt.org",
    SRV: "Priority weight port target, for example 10 5 443 service.example.com.",
  }[type];
}

export default function DnsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainId, setDomainId] = useState("");
  const [zone, setZone] = useState<Zone | null>(null);
  const [nameservers, setNameservers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [showRecord, setShowRecord] = useState(false);
  const [type, setType] = useState<RecordType>("A");
  const [name, setName] = useState("@");
  const [ttl, setTtl] = useState(3600);
  const [value, setValue] = useState("");
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Rrset | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [importText, setImportText] = useState("");
  const [importPreview, setImportPreview] = useState<Rrset[]>([]);

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const selectedDomain = useMemo(() => domains.find((row) => row.id === domainId), [domains, domainId]);
  const canManage = Boolean(me?.is_platform_owner || ["tenant_admin", "dns_admin"].includes(selectedContext?.role || ""));
  const verified = Boolean(selectedDomain?.status === "verified" && selectedDomain?.ownership_verified_at);
  const rrsets = zone?.rrsets || [];

  useEffect(() => {
    void (async () => {
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
          const response = await api("/tenants");
          const data = response.ok ? await response.json() : [];
          rows = data.map((item: { id: string; name: string; status: string }) => ({
            tenant_id: item.id,
            tenant_name: item.name,
            role: "platform_owner",
            status: item.status,
          }));
        } else {
          const response = await api("/me/memberships");
          rows = response.ok ? await response.json() : [];
        }
        rows = rows.filter((row) => row.status === "active");
        setContexts(rows);
        const remembered = localStorage.getItem("mailbox_dns_tenant");
        setTenantId(rows.find((row) => row.tenant_id === remembered)?.tenant_id || rows[0]?.tenant_id || "");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Unable to initialize DNS management");
      }
    })();
  }, [router]);

  useEffect(() => {
    if (!tenantId) {
      setDomains([]);
      setDomainId("");
      return;
    }
    localStorage.setItem("mailbox_dns_tenant", tenantId);
    void (async () => {
      const response = await api(`/tenants/${tenantId}/domains`);
      if (!response.ok) {
        setError(await detail(response, "Unable to load domains"));
        return;
      }
      const data = await response.json();
      const eligible: Domain[] = (data.items || []).filter(
        (domain: Domain) =>
          domain.dns_mode === "platform" &&
          (domain.status === "pending_verification" || domain.status === "verified"),
      );
      setDomains(eligible);
      setDomainId((current) => (eligible.some((domain) => domain.id === current) ? current : eligible[0]?.id || ""));
    })();
  }, [tenantId]);

  useEffect(() => {
    setZone(null);
    setNameservers([]);
    if (tenantId && domainId) void loadZone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, domainId]);

  async function loadZone() {
    if (!tenantId || !domainId) return;
    setBusy(true);
    setError("");
    try {
      const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/zone`);
      if (response.ok) {
        setZone(await response.json());
      } else if (response.status === 404) {
        setZone(null);
      } else {
        throw new Error(await detail(response, "Unable to load authoritative zone"));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load authoritative zone");
      setZone(null);
    } finally {
      setBusy(false);
    }
  }

  async function provision() {
    if (!tenantId || !domainId) return;
    setBusy(true);
    setError("");
    try {
      const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/zone`, { method: "POST" });
      if (!response.ok) throw new Error(await detail(response, "Unable to prepare authoritative zone"));
      const data = await response.json();
      setZone(data.zone);
      setNameservers(data.required_nameservers || []);
      if (data.staged) {
        setToast(
          data.created
            ? "Staged PowerDNS zone prepared. Add/import all records before changing registrar nameservers."
            : "Staged PowerDNS zone reconciled. Check all records before changing registrar nameservers.",
        );
      } else {
        setToast(data.created ? "Authoritative zone created and activated." : "Authoritative zone reconciled.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to prepare authoritative zone");
    } finally {
      setBusy(false);
    }
  }

  const owner = selectedDomain?.ascii_name || "";
  const ownerFqdn = name === "@" ? owner : name.endsWith(owner) ? name : `${name}.${owner}`;
  const conflicts = useMemo(() => {
    const problems: string[] = [];
    if (type === "CNAME" && name === "@") problems.push("CNAME cannot be used at the zone apex.");
    const same = rrsets.filter((row) => row.name.replace(/\.$/, "") === ownerFqdn.replace(/\.$/, ""));
    if (type === "CNAME" && same.some((row) => row.type !== "CNAME" && !["SOA", "NS"].includes(row.type))) {
      problems.push("This owner already has another record type; CNAME cannot coexist with ordinary records.");
    }
    if (type !== "CNAME" && same.some((row) => row.type === "CNAME")) {
      problems.push("This owner already has a CNAME; remove it before adding another record type.");
    }
    if (["MX", "NS"].includes(type) && name !== "@") problems.push(`${type} records are usually managed at the zone apex.`);
    return problems;
  }, [name, ownerFqdn, rrsets, type]);

  async function saveRecord(event: FormEvent) {
    event.preventDefault();
    if (!tenantId || !domainId || conflicts.length) return;
    setBusy(true);
    setError("");
    try {
      const contents = value.split("\n").map((row) => row.trim()).filter(Boolean);
      const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/records`, {
        method: "PUT",
        body: JSON.stringify({ name, type, ttl, contents }),
      });
      if (!response.ok) throw new Error(await detail(response, "Unable to save DNS record"));
      setToast(verified ? "DNS record set saved." : "DNS record staged. It will become public only after registrar delegation.");
      setShowRecord(false);
      setName("@");
      setType("A");
      setTtl(3600);
      setValue("");
      await loadZone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save DNS record");
    } finally {
      setBusy(false);
    }
  }

  async function removeRecord() {
    if (!pendingDelete || !tenantId || !domainId) return;
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ name: pendingDelete.name, type: pendingDelete.type });
      const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/records?${params}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await detail(response, "Unable to delete DNS record"));
      setPendingDelete(null);
      setConfirmText("");
      setToast(verified ? "DNS record set deleted." : "Staged DNS record set deleted.");
      await loadZone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete DNS record");
    } finally {
      setBusy(false);
    }
  }

  function copy(text: string) {
    void navigator.clipboard.writeText(text);
    setToast("Copied to clipboard.");
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify({ zone: selectedDomain?.ascii_name, rrsets }, null, 2)], { type: "application/json" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `${selectedDomain?.ascii_name || "zone"}.json`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  function exportCsv() {
    const rows = [
      "name,type,ttl,content",
      ...rrsets.flatMap((rrset) => rrset.records.map((record) => [rrset.name, rrset.type, rrset.ttl, JSON.stringify(record.content)].join(","))),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `${selectedDomain?.ascii_name || "zone"}.csv`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  function previewImport() {
    try {
      const parsed = JSON.parse(importText);
      const list: Rrset[] = Array.isArray(parsed) ? parsed : parsed.rrsets;
      if (!Array.isArray(list)) throw new Error("JSON must contain an rrsets array");
      setImportPreview(list.filter((row) => row && row.name && row.type && Array.isArray(row.records)));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invalid import file");
    }
  }

  async function applyImport() {
    if (!tenantId || !domainId) return;
    setBusy(true);
    setError("");
    try {
      for (const rrset of importPreview) {
        if (["SOA", "NS"].includes(rrset.type)) continue;
        const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/records`, {
          method: "PUT",
          body: JSON.stringify({
            name: rrset.name,
            type: rrset.type,
            ttl: rrset.ttl || 3600,
            contents: rrset.records.map((record) => record.content),
          }),
        });
        if (!response.ok) throw new Error(`Import stopped at ${rrset.type} ${rrset.name}: ${await detail(response, "record rejected")}`);
      }
      setImportPreview([]);
      setImportText("");
      setToast(verified ? "DNS import applied successfully." : "DNS import staged successfully. Review it before registrar cutover.");
      await loadZone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to apply DNS import");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ControlShell title="Authoritative DNS" subtitle="PowerDNS zones, records and safe change workflows" userEmail={me?.email}>
      <div className="space-y-4">
        <PageHeader
          eyebrow="Authoritative DNS"
          title="Zone control"
          description="Stage a PowerDNS zone and records before registrar cutover, then verify delegation and activate the live DNS/mail lifecycle."
          actions={<>
            <select className="input min-w-[190px]" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>
              <option value="">Select organization</option>
              {contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}
            </select>
            <select className="input min-w-[240px]" value={domainId} onChange={(event) => setDomainId(event.target.value)}>
              <option value="">Select platform domain</option>
              {domains.map((domain) => <option key={domain.id} value={domain.id}>{domain.unicode_name}{domain.status === "pending_verification" ? " · pending" : " · verified"}</option>)}
            </select>
          </>}
        />

        {error ? <div className="surface-card border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700"><AlertTriangle size={14} className="mr-2 inline"/>{error}</div> : null}

        {!domains.length && tenantId ? <EmptyState
          icon={<Server size={20}/>}
          title="No Platform DNS domains"
          description="Add a domain in Domain portfolio and choose Mailbox DNS / PowerDNS. Pending domains can now be staged before ownership verification."
          action={<a className="btn-primary" href="/domains">Open domains</a>}
        /> : null}

        {selectedDomain && !verified ? <section className="surface-card border-amber-200 bg-amber-50/60 p-4">
          <div className="flex items-start gap-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-800"><Database size={16}/></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black text-[var(--admin-ink)]">Staged DNS · safe registrar cutover</p>
              <p className="mt-1 text-[11px] leading-5 text-[var(--admin-muted)]">This domain is not verified yet. Prepare the zone and all required records first. Staging does not activate Mailbox mail routing or DKIM/Rspamd lifecycle.</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                {[
                  ["1", "Prepare zone", zone ? "Done" : "Next"],
                  ["2", "Add / import records", zone ? "Available" : "After step 1"],
                  ["3", "Change registrar NS", "After records are ready"],
                  ["4", "Wait for propagation", "Both Ithute NS"],
                  ["5", "Verify ownership", "Domain portfolio"],
                ].map(([number, label, state]) => <div key={number} className="rounded-xl border border-amber-200 bg-white p-3">
                  <div className="flex items-center gap-2"><span className="grid h-5 w-5 place-items-center rounded-full bg-[#123a38] text-[9px] font-black text-white">{number}</span><span className="text-[10px] font-black">{label}</span></div>
                  <p className="mt-1 text-[9px] text-[var(--admin-muted)]">{state}</p>
                </div>)}
              </div>
              {zone ? <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-semibold text-emerald-800"><CheckCircle2 size={14}/>Zone is staged. Finish checking records before changing nameservers at Zeecom. <a href="/domains" className="font-black underline">Verify after delegation propagates</a></div> : null}
            </div>
          </div>
        </section> : null}

        {selectedDomain ? <section className="grid gap-4 xl:grid-cols-[.72fr_1.28fr]">
          <aside className="surface-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div><p className="eyebrow-label">Selected zone</p><p className="mt-2 break-all text-lg font-black">{selectedDomain.ascii_name}</p></div>
              <StatusBadge state={zone ? (verified ? "good" : "warn") : "warn"}>{zone ? (verified ? "Provisioned" : "Staged") : "Needs preparation"}</StatusBadge>
            </div>
            <div className="mt-5 space-y-3 text-[11px]">
              <div className="flex justify-between border-b pb-2"><span className="text-[var(--admin-muted)]">Ownership</span><strong>{verified ? "Verified" : "Pending"}</strong></div>
              <div className="flex justify-between border-b pb-2"><span className="text-[var(--admin-muted)]">Kind</span><strong>{zone?.kind || "—"}</strong></div>
              <div className="flex justify-between border-b pb-2"><span className="text-[var(--admin-muted)]">Serial</span><strong>{zone?.serial || "—"}</strong></div>
              <div className="flex justify-between"><span className="text-[var(--admin-muted)]">RRsets</span><strong>{rrsets.length}</strong></div>
            </div>
            {nameservers.length ? <div className="mt-4 rounded-xl bg-[#f6f8f6] p-3">
              <p className="eyebrow-label">Registrar nameservers</p>
              {nameservers.map((nameserver) => <div key={nameserver} className="mt-1 flex items-center gap-2"><code className="min-w-0 flex-1 truncate text-[10px]">{nameserver}</code><button type="button" onClick={() => copy(nameserver)} className="icon-button" aria-label={`Copy ${nameserver}`}><Copy size={12}/></button></div>)}
              {!verified ? <p className="mt-2 text-[9px] leading-4 text-amber-800">Only change the registrar to these nameservers after the staged zone contains every record you need.</p> : null}
            </div> : null}
            <div className="mt-5 flex flex-wrap gap-2">
              {canManage ? <button className="btn-primary" disabled={busy} onClick={() => void provision()}><Database size={14}/>{zone ? (verified ? "Reconcile" : "Reconcile staged zone") : "Prepare zone"}</button> : null}
              <button className="btn-secondary" disabled={busy} onClick={() => void loadZone()}><RefreshCw size={14} className={busy ? "animate-spin" : ""}/>Refresh</button>
              {zone ? <><button className="btn-secondary" onClick={exportJson}><Download size={14}/>JSON</button><button className="btn-secondary" onClick={exportCsv}><Download size={14}/>CSV</button></> : null}
            </div>
          </aside>

          <div className="space-y-4">
            <section className="surface-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><p className="text-sm font-black">DNS record sets</p><p className="text-[10px] text-[var(--admin-muted)]">SOA and NS are protected. Pending-domain records are staged until registrar delegation.</p></div>
                {zone && canManage ? <button className="btn-primary" onClick={() => setShowRecord(true)}><Plus size={14}/>Add record</button> : null}
              </div>
              {!zone ? <div className="mt-4 rounded-xl border border-dashed border-[var(--admin-line)] bg-[var(--admin-soft)] p-5 text-center text-[11px] text-[var(--admin-muted)]">Click <b>Prepare zone</b> first. After that you can add or import records before verification.</div> : <div className="table-wrap mt-4"><table><thead><tr><th>Name</th><th>Type</th><th>TTL</th><th>Values</th><th/></tr></thead><tbody>
                {rrsets.map((rrset) => <tr key={`${rrset.name}-${rrset.type}`}><td><code className="text-[10px]">{rrset.name}</code></td><td><StatusBadge state="neutral">{rrset.type}</StatusBadge></td><td className="text-[10px]">{rrset.ttl}</td><td>{rrset.records.map((record, index) => <code key={index} className="block max-w-[460px] overflow-x-auto text-[10px]">{record.content}</code>)}</td><td>{canManage && !["SOA", "NS"].includes(rrset.type) ? <button className="icon-button text-red-700" onClick={() => { setPendingDelete(rrset); setConfirmText(""); }} aria-label={`Delete ${rrset.type} ${rrset.name}`}><Trash2 size={13}/></button> : null}</td></tr>)}
                {!rrsets.length ? <tr><td colSpan={5} className="py-8 text-center text-[var(--admin-muted)]">No records yet. Add the first record set before registrar cutover.</td></tr> : null}
              </tbody></table></div>}
            </section>

            {zone && canManage ? <section className="surface-card p-4">
              <div className="flex items-center gap-2"><Upload size={16}/><div><p className="text-sm font-black">Import with preview</p><p className="text-[10px] text-[var(--admin-muted)]">Paste a previous Mailbox DNS JSON export. SOA/NS rows are skipped automatically.</p></div></div>
              <textarea className="input mt-3 min-h-24 font-mono text-[10px]" value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='{"rrsets": [...]}'/>
              <div className="mt-3 flex gap-2"><button className="btn-secondary" type="button" onClick={previewImport}>Preview import</button>{importPreview.length ? <button className="btn-primary" type="button" disabled={busy} onClick={() => void applyImport()}>Apply {importPreview.length} RRsets</button> : null}</div>
              {importPreview.length ? <div className="mt-3 rounded-xl bg-[#f7f9f7] p-3 text-[10px]"><strong>Change preview</strong>{importPreview.slice(0, 12).map((rrset, index) => <div key={index} className="mt-1 font-mono">+ {rrset.name} {rrset.type} {rrset.ttl}</div>)}{importPreview.length > 12 ? <div className="mt-1">+ {importPreview.length - 12} more…</div> : null}</div> : null}
            </section> : null}
          </div>
        </section> : null}
      </div>

      {showRecord ? <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setShowRecord(false); }}>
        <form onSubmit={saveRecord} className="w-full max-w-xl rounded-2xl bg-white p-5 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="record-title">
          <div className="flex items-start justify-between gap-4"><div><p id="record-title" className="text-lg font-black">Add DNS record set</p><p className="mt-1 text-[11px] text-[var(--admin-muted)]">{verified ? "This record will be written to the authoritative zone." : "This record is staged and will become public only after registrar delegation."}</p></div><button className="icon-button" type="button" onClick={() => setShowRecord(false)} aria-label="Close"><X size={15}/></button></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label><span className="label">Record type</span><select className="input" value={type} onChange={(event) => setType(event.target.value as RecordType)}>{(["A", "AAAA", "CNAME", "MX", "TXT", "CAA", "SRV"] as RecordType[]).map((recordType) => <option key={recordType}>{recordType}</option>)}</select></label>
            <label><span className="label">Name</span><input className="input font-mono" value={name} onChange={(event) => setName(event.target.value)} placeholder="@"/></label>
            <label><span className="label">TTL</span><input className="input" type="number" min={60} max={86400} value={ttl} onChange={(event) => setTtl(Number(event.target.value))}/></label>
            <div className="sm:col-span-2"><span className="label">Value{type === "TXT" ? " / text" : ""}</span><textarea className="input min-h-28 font-mono text-[11px]" value={value} onChange={(event) => setValue(event.target.value)} placeholder={help(type)}/><p className="helper">{help(type)} One value per line when the record set contains multiple values.</p></div>
          </div>
          {conflicts.length ? <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] font-semibold text-amber-900">{conflicts.map((problem) => <div key={problem}>• {problem}</div>)}</div> : null}
          <div className="mt-5 flex justify-end gap-2"><button type="button" className="btn-secondary" disabled={busy} onClick={() => setShowRecord(false)}>Cancel</button><button type="submit" className="btn-primary" disabled={busy || !value.trim() || conflicts.length > 0}><Plus size={14}/>{verified ? "Save record" : "Stage record"}</button></div>
        </form>
      </div> : null}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete DNS record set"
        description={pendingDelete ? `Delete ${pendingDelete.type} ${pendingDelete.name}? SOA and NS records cannot be deleted here.` : "Delete this DNS record set?"}
        confirmLabel="Delete record"
        dangerous
        requireText={pendingDelete?.name}
        value={confirmText}
        onValueChange={setConfirmText}
        onCancel={() => { setPendingDelete(null); setConfirmText(""); }}
        onConfirm={() => void removeRecord()}
      />
      {toast ? <Toast tone="success" message={toast} onClose={() => setToast("")}/> : null}
    </ControlShell>
  );
}
