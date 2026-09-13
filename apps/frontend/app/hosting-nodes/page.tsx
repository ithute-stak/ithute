"use client";

import { useEffect, useState } from "react";
import { Copy, KeyRound, RefreshCw, Server, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Node = {
  id: string;
  name: string;
  hostname: string;
  public_ip?: string | null;
  status: string;
  accepts_new_projects: boolean;
  allocatable: { storage_mb: number; memory_mb: number; cpu_millicores: number };
  allocated: { storage_mb: number; memory_mb: number; cpu_millicores: number; projects: number };
  available: { storage_mb: number; memory_mb: number; cpu_millicores: number };
};
type Agent = { node_id: string; configured: boolean; token_hint?: string | null; agent_version?: string | null; last_seen_at?: string | null; rotated_at?: string | null };

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

function gb(mb: number) { return `${(mb / 1024).toFixed(mb % 1024 ? 1 : 0)} GB`; }
function cpu(millicores: number) { return `${(millicores / 1000).toFixed(2)} CPU`; }

export default function HostingNodesPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [agents, setAgents] = useState<Record<string, Agent>>({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [newToken, setNewToken] = useState<{ node: string; token: string } | null>(null);

  async function load() {
    setLoading(true); setError("");
    const response = await api("/platform/hosting/nodes");
    if (!response.ok) { setError(await detail(response, "Unable to load hosting nodes.")); setLoading(false); return; }
    const rows: Node[] = (await response.json()).items || [];
    setNodes(rows);
    const states = await Promise.all(rows.map(async (node) => {
      const agentResponse = await api(`/platform/hosting/nodes/${node.id}/agent`);
      return [node.id, agentResponse.ok ? await agentResponse.json() : { node_id: node.id, configured: false }] as const;
    }));
    setAgents(Object.fromEntries(states));
    setLoading(false);
  }

  useEffect(() => {
    void (async () => {
      const response = await api("/auth/me");
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) return;
      const current: Me = await response.json();
      setMe(current);
      if (!current.is_platform_owner) { setError("Only the system owner can manage hosting-node credentials."); setLoading(false); return; }
      await load();
    })();
  }, [router]);

  async function rotate(node: Node) {
    if (!window.confirm(`Rotate the hosting-agent credential for ${node.name}? The previous credential stops working immediately.`)) return;
    setMessage(""); setError(""); setNewToken(null);
    const response = await api(`/platform/hosting/nodes/${node.id}/agent-token`, { method: "POST" });
    if (!response.ok) { setError(await detail(response, "Unable to rotate node credential.")); return; }
    const body = await response.json();
    setNewToken({ node: node.name, token: body.token });
    setMessage(`New credential created for ${node.name}. It is shown once only.`);
    await load();
  }

  async function copyToken() {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken.token);
    setMessage(`Credential for ${newToken.node} copied. Store it only on that hosting node.`);
  }

  return <ControlShell title="Hosting nodes" subtitle="System-owner capacity and host-agent trust boundary" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="System owner" title="Hosting node agents" description="Each shared hosting node uses a separate one-time credential to claim only the releases assigned to that node. Customer accounts never receive this credential or Docker-host access." />

      {newToken ? <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5"><div className="flex items-start gap-3"><ShieldAlert className="mt-0.5 shrink-0 text-amber-700" size={19}/><div className="min-w-0 flex-1"><h2 className="text-sm font-black text-amber-950">Save this credential now — it will not be shown again</h2><p className="mt-1 text-[10px] leading-5 text-amber-900">Install it only in the root-owned configuration for <b>{newToken.node}</b>. Rotating again immediately invalidates this token.</p><div className="mt-3 flex items-center gap-2"><code className="min-w-0 flex-1 break-all rounded-xl border border-amber-200 bg-white p-3 text-[10px] text-[#263a31]">{newToken.token}</code><button className="btn-secondary shrink-0" onClick={() => void copyToken()}><Copy size={13}/>Copy</button></div></div></div></section> : null}

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <section className="surface-card p-4 sm:p-5"><div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black">Registered hosting nodes</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Capacity is configured under Packages & Capacity. This page controls the node-agent identity only.</p></div><button className="icon-button" aria-label="Refresh hosting nodes" disabled={!me?.is_platform_owner} onClick={() => void load()}><RefreshCw size={15}/></button></div>{loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading hosting nodes…</p> : <div className="mt-5 grid gap-4 xl:grid-cols-2">{nodes.map((node) => { const agent = agents[node.id]; return <article key={node.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Server size={18}/></span><div><h3 className="text-sm font-black">{node.name}</h3><p className="mt-0.5 text-[9px] text-[var(--admin-muted)]">{node.hostname}{node.public_ip ? ` · ${node.public_ip}` : ""}</p></div></div><span className={`rounded-full px-2 py-1 text-[9px] font-black ${node.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{node.status}</span></div><div className="mt-4 grid grid-cols-3 gap-2 text-[9px]"><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{gb(node.available.storage_mb)}</b><br/>storage free</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{node.available.memory_mb} MB</b><br/>RAM free</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{cpu(node.available.cpu_millicores)}</b><br/>CPU free</div></div><div className="mt-4 rounded-xl border border-[#e4e9e6] p-3"><div className="flex items-center justify-between gap-3"><div><p className="text-[10px] font-black">Node agent</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{agent?.configured ? `Configured · ${agent.token_hint || "credential hidden"}` : "No agent credential yet"}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{agent?.last_seen_at ? `Last seen ${new Date(agent.last_seen_at).toLocaleString()}${agent.agent_version ? ` · ${agent.agent_version}` : ""}` : "No heartbeat received yet"}</p></div><button className="btn-secondary shrink-0" onClick={() => void rotate(node)}><KeyRound size={13}/>{agent?.configured ? "Rotate" : "Create credential"}</button></div></div></article>; })}{!nodes.length ? <p className="text-xs text-[var(--admin-muted)]">No hosting nodes are registered yet. Create sellable capacity from Packages & Capacity first.</p> : null}</div>}</section>
    </div>
  </ControlShell>;
}
