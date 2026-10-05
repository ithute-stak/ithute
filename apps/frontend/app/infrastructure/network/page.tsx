"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Activity, Network, RefreshCw, Server, ShieldCheck, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";
import { apiFetch } from "@/lib/platform-api";

type Me = { email: string; is_platform_owner: boolean };
type Peer = {
  id: string;
  server_id: string;
  public_key: string;
  assigned_ipv4: string;
  status: string;
  last_handshake_at?: string | null;
  rx_bytes?: number | null;
  tx_bytes?: number | null;
};
type Mesh = {
  configured: boolean;
  interface: string;
  subnet: string;
  edge_address: string;
  listen_port: number;
  edge_public_key?: string | null;
  edge_endpoint?: string | null;
  reconciler_configured: boolean;
  policy_mode: "full_mesh";
  peer_communication_default: "allow";
  items: Peer[];
};

type ServerOption = {
  id: string;
  name: string;
  hostname: string;
  status: string;
};

type NetworkGrant = {
  id: string;
  source_server_id: string;
  source_name?: string | null;
  source_ipv4?: string | null;
  target_server_id: string;
  target_name?: string | null;
  target_ipv4?: string | null;
  protocol: "tcp" | "udp";
  port: number;
  service: string;
  enabled: boolean;
};

async function api(path: string, init: RequestInit = {}) {
  return apiFetch(path, init);
}

function bytes(value?: number | null) {
  if (value === null || value === undefined) return "—";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function fresh(value?: string | null) {
  if (!value) return false;
  const time = new Date(value).getTime();
  return Number.isFinite(time) && Date.now() - time <= 180000;
}

export default function PrivateNetworkPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [mesh, setMesh] = useState<Mesh | null>(null);
  const [servers, setServers] = useState<ServerOption[]>([]);
  const [grants, setGrants] = useState<NetworkGrant[]>([]);
  const [savingGrant, setSavingGrant] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const connected = useMemo(() => mesh?.items.filter((peer) => fresh(peer.last_handshake_at)).length || 0, [mesh]);

  async function load() {
    setLoading(true); setError("");
    const [meshResponse, serversResponse, grantsResponse] = await Promise.all([
      api("/platform/infrastructure/private-network"),
      api("/platform/infrastructure/servers"),
      api("/platform/infrastructure/private-network/grants"),
    ]);
    if (!meshResponse.ok) {
      const body = await meshResponse.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Unable to load the private network.");
      setLoading(false);
      return;
    }
    setMesh(await meshResponse.json());
    if (serversResponse.ok) {
      const body = await serversResponse.json();
      setServers(Array.isArray(body.items) ? body.items : []);
    }
    if (grantsResponse.ok) {
      const body = await grantsResponse.json();
      setGrants(Array.isArray(body.items) ? body.items : []);
    }
    setLoading(false);
  }

  async function createGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingGrant(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await api("/platform/infrastructure/private-network/grants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_server_id: String(form.get("source_server_id") || ""),
        target_server_id: String(form.get("target_server_id") || ""),
        protocol: String(form.get("protocol") || "tcp"),
        port: Number(form.get("port") || 0),
        service: String(form.get("service") || "").trim(),
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Unable to create the private service grant.");
      setSavingGrant(false);
      return;
    }
    event.currentTarget.reset();
    await load();
    setSavingGrant(false);
  }

  async function removeGrant(grantId: string) {
    setError("");
    const response = await api(`/platform/infrastructure/private-network/grants/${grantId}`, { method: "DELETE" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Unable to remove the private service grant.");
      return;
    }
    await load();
  }

  useEffect(() => {
    void (async () => {
      const response = await api("/auth/me");
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) { setLoading(false); return; }
      const current: Me = await response.json();
      setMe(current);
      if (!current.is_platform_owner) { setError("Platform owner access is required."); setLoading(false); return; }
      await load();
    })();
  }, [router]);

  return <ControlShell title="Private network" subtitle="Ithute-managed server-to-edge connectivity" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader
        eyebrow="Infrastructure"
        title="Managed private network"
        description="Ithute allocates private addresses and connects enrolled nodes in a private full mesh. Every enrolled node can communicate with every other enrolled node by default."
      />

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {mesh ? <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="surface-card p-4"><Network size={18}/><p className="mt-3 text-lg font-black">{mesh.subnet}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Mesh subnet</p></div>
          <div className="surface-card p-4"><Server size={18}/><p className="mt-3 text-lg font-black">{mesh.edge_address}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Edge address</p></div>
          <div className="surface-card p-4"><Activity size={18}/><p className="mt-3 text-2xl font-black">{connected}/{mesh.items.length}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Recent handshakes</p></div>
          <div className="surface-card p-4"><ShieldCheck size={18}/><p className="mt-3 text-lg font-black">{mesh.policy_mode === "full_mesh" ? "Full mesh" : "Setup required"}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Peer communication</p></div>
        </section>

        <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-black">Edge configuration</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">The edge private key is never stored in Ithute's database.</p></div><button className="icon-button" onClick={() => void load()} aria-label="Refresh private network"><RefreshCw size={14}/></button></div>
          <div className="mt-4 grid gap-2 text-[10px] sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl bg-[#f5f8f6] p-3"><b>Endpoint</b><p className="mt-1 break-all">{mesh.edge_endpoint || "Not configured"}</p></div>
            <div className="rounded-xl bg-[#f5f8f6] p-3"><b>Listen port</b><p className="mt-1">{mesh.listen_port}</p></div>
            <div className="rounded-xl bg-[#f5f8f6] p-3"><b>Edge public key</b><p className="mt-1 break-all">{mesh.edge_public_key || "Not configured"}</p></div>
            <div className="rounded-xl bg-[#f5f8f6] p-3"><b>Reconciler credential</b><p className="mt-1">{mesh.reconciler_configured ? "Configured" : "Missing"}</p></div>
          </div>
        </section>

        <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-black">Service relationship map</h2>
              <p className="mt-1 text-[10px] text-[var(--admin-muted)]">All enrolled nodes can already communicate over the private mesh. These optional records document which services are intended to talk to each other.</p>
            </div>
            <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[9px] font-black text-emerald-700">Default allow · private mesh</span>
          </div>

          <form onSubmit={createGrant} className="mt-4 grid gap-3 rounded-2xl border border-[#dce5e0] bg-[#f8faf9] p-4 md:grid-cols-2 xl:grid-cols-6">
            <label className="text-[10px] font-bold">Source VPS
              <select name="source_server_id" required defaultValue="" className="mt-1 min-h-10 w-full rounded-xl border border-[#dce5e0] bg-white px-3 text-xs">
                <option value="" disabled>Select source</option>
                {servers.filter((server) => server.status === "active").map((server) => <option key={server.id} value={server.id}>{server.name} · {server.hostname}</option>)}
              </select>
            </label>
            <label className="text-[10px] font-bold">Target VPS
              <select name="target_server_id" required defaultValue="" className="mt-1 min-h-10 w-full rounded-xl border border-[#dce5e0] bg-white px-3 text-xs">
                <option value="" disabled>Select target</option>
                {servers.filter((server) => server.status === "active").map((server) => <option key={server.id} value={server.id}>{server.name} · {server.hostname}</option>)}
              </select>
            </label>
            <label className="text-[10px] font-bold">Protocol
              <select name="protocol" defaultValue="tcp" className="mt-1 min-h-10 w-full rounded-xl border border-[#dce5e0] bg-white px-3 text-xs">
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
              </select>
            </label>
            <label className="text-[10px] font-bold">Port
              <input name="port" type="number" min={1} max={65535} required placeholder="5432" className="mt-1 min-h-10 w-full rounded-xl border border-[#dce5e0] bg-white px-3 text-xs" />
            </label>
            <label className="text-[10px] font-bold">Service
              <input name="service" required maxLength={80} placeholder="PostgreSQL" className="mt-1 min-h-10 w-full rounded-xl border border-[#dce5e0] bg-white px-3 text-xs" />
            </label>
            <div className="flex items-end">
              <button type="submit" disabled={savingGrant} className="btn-primary min-h-10 w-full">{savingGrant ? "Saving…" : "Record service"}</button>
            </div>
          </form>

          <div className="mt-4 space-y-2">
            {grants.map((grant) => <article key={grant.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-[#dce5e0] bg-white px-3 py-3 text-[10px]">
              <ShieldCheck size={15} className="text-emerald-700" />
              <div className="min-w-0 flex-1">
                <p className="font-black">{grant.source_name || grant.source_server_id} <span className="font-normal text-[var(--admin-muted)]">→</span> {grant.target_name || grant.target_server_id}</p>
                <p className="mt-0.5 text-[var(--admin-muted)]">{grant.source_ipv4 || "awaiting private IP"} → {grant.target_ipv4 || "awaiting private IP"} · {grant.protocol.toUpperCase()}/{grant.port} · {grant.service}</p>
              </div>
              <button type="button" onClick={() => void removeGrant(grant.id)} className="icon-button text-red-700" aria-label={`Remove ${grant.service} grant`}><Trash2 size={14}/></button>
            </article>)}
            {!grants.length ? <p className="text-xs text-[var(--admin-muted)]">No service relationships are documented yet. Node-to-node private communication is still enabled by default.</p> : null}
          </div>
        </section>

        <section className="surface-card p-4 sm:p-5">
          <h2 className="text-sm font-black">Hosting VPS peers</h2>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {mesh.items.map((peer) => <article key={peer.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4">
              <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-black">{peer.assigned_ipv4}</p><p className="mt-1 break-all text-[9px] text-[var(--admin-muted)]">{peer.public_key}</p></div><span className={`rounded-full px-2.5 py-1 text-[9px] font-black ${fresh(peer.last_handshake_at) ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{fresh(peer.last_handshake_at) ? "connected" : "waiting"}</span></div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[9px]"><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{peer.last_handshake_at ? new Date(peer.last_handshake_at).toLocaleString() : "Never"}</b><br/>last handshake</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{bytes(peer.rx_bytes)}</b><br/>received</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{bytes(peer.tx_bytes)}</b><br/>sent</div></div>
            </article>)}
            {!mesh.items.length ? <p className="text-xs text-[var(--admin-muted)]">No hosting VPS has enrolled in the managed private network yet.</p> : null}
          </div>
        </section>
      </> : loading ? <p className="text-xs text-[var(--admin-muted)]">Loading private network…</p> : null}
    </div>
  </ControlShell>;
}
