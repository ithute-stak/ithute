"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, KeyRound, Network, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

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
  items: Peer[];
};

async function api(path: string) {
  let response = await fetch(`${API}${path}`, { credentials: "include" });
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, { credentials: "include" });
  }
  return response;
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const connected = useMemo(() => mesh?.items.filter((peer) => fresh(peer.last_handshake_at)).length || 0, [mesh]);

  async function load() {
    setLoading(true); setError("");
    const response = await api("/platform/infrastructure/private-network");
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(typeof body.detail === "string" ? body.detail : "Unable to load the private network.");
      setLoading(false);
      return;
    }
    setMesh(await response.json());
    setLoading(false);
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
        description="Ithute allocates private addresses and synchronizes approved hosting-node public keys to the edge. Node private keys remain on their VPS."
      />

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {mesh ? <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="surface-card p-4"><Network size={18}/><p className="mt-3 text-lg font-black">{mesh.subnet}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Mesh subnet</p></div>
          <div className="surface-card p-4"><Server size={18}/><p className="mt-3 text-lg font-black">{mesh.edge_address}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Edge address</p></div>
          <div className="surface-card p-4"><Activity size={18}/><p className="mt-3 text-2xl font-black">{connected}/{mesh.items.length}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Recent handshakes</p></div>
          <div className="surface-card p-4"><ShieldCheck size={18}/><p className="mt-3 text-lg font-black">{mesh.configured ? "Ready" : "Setup required"}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Edge control plane</p></div>
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
