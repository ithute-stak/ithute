"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Copy, KeyRound, Network, RefreshCw, Server, ShieldAlert, TerminalSquare } from "lucide-react";
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
type Agent = { node_id: string; configured: boolean; token_hint?: string | null; agent_version?: string | null; last_seen_at?: string | null; origin_bind_ip?: string | null; rotated_at?: string | null };
type Onboarding = {
  node_id: string;
  ready: boolean;
  active: boolean;
  origin_bind_ip?: string | null;
  hosting_agent_version?: string | null;
  server_agent_version?: string | null;
  checks: Record<string, boolean>;
  managed_network_ip?: string | null;
  managed_network_last_handshake_at?: string | null;
  automation_enabled?: boolean;
  health_status?: string;
  healthy_since?: string | null;
  unhealthy_since?: string | null;
  last_transition?: string | null;
  last_transition_at?: string | null;
  last_reason?: string | null;
  thresholds?: {
    auto_activate_seconds: number;
    auto_drain_seconds: number;
    auto_recover_seconds: number;
    heartbeat_grace_seconds: number;
  };
};
type Bootstrap = { node_id: string; node: string; token: string; script_path: string; expires_at: string };

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
  const [onboarding, setOnboarding] = useState<Record<string, Onboarding>>({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [newToken, setNewToken] = useState<{ node: string; token: string } | null>(null);
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [backupRemotes, setBackupRemotes] = useState<Record<string, string>>({});

  async function load(silent = false) {
    if (!silent) setLoading(true); setError("");
    const response = await api("/platform/hosting/nodes");
    if (!response.ok) { setError(await detail(response, "Unable to load hosting nodes.")); setLoading(false); return; }
    const rows: Node[] = (await response.json()).items || [];
    setNodes(rows);
    const states = await Promise.all(rows.map(async (node) => {
      const [agentResponse, onboardingResponse] = await Promise.all([
        api(`/platform/hosting/nodes/${node.id}/agent`),
        api(`/platform/hosting/nodes/${node.id}/onboarding`),
      ]);
      return {
        nodeId: node.id,
        agent: agentResponse.ok ? await agentResponse.json() : { node_id: node.id, configured: false },
        onboarding: onboardingResponse.ok ? await onboardingResponse.json() : null,
      };
    }));
    setAgents(Object.fromEntries(states.map((row) => [row.nodeId, row.agent])));
    setOnboarding(Object.fromEntries(states.filter((row) => row.onboarding).map((row) => [row.nodeId, row.onboarding])));
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

  useEffect(() => {
    if (!me?.is_platform_owner) return;
    const timer = window.setInterval(() => void load(true), 15000);
    return () => window.clearInterval(timer);
  }, [me?.is_platform_owner]);

  async function setAutomation(node: Node, enabled: boolean) {
    setMessage(""); setError("");
    const response = await api(`/platform/hosting/nodes/${node.id}/automation`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to update node automation.")); return; }
    setMessage(enabled
      ? `Automatic activation and self-healing enabled for ${node.name}.`
      : `${node.name} is on manual hold. Ithute will not change its scheduling state automatically.`);
    await load(true);
  }

  async function createBootstrap(node: Node) {
    setMessage(""); setError(""); setBootstrap(null); setNewToken(null);
    const response = await api(`/platform/hosting/nodes/${node.id}/bootstrap`, {
      method: "POST",
      body: JSON.stringify({
        managed_private_network: true,
        backup_remote: (backupRemotes[node.id] || "").trim() || null,
      }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to create secure onboarding token.")); return; }
    const body = await response.json();
    setBootstrap({ node_id: node.id, node: node.name, token: body.token, script_path: body.script_path, expires_at: body.expires_at });
    setMessage(`Secure 15-minute onboarding token created for ${node.name}. The node has been drained until readiness checks pass.`);
    await load();
  }

  async function copyBootstrapToken() {
    if (!bootstrap) return;
    await navigator.clipboard.writeText(bootstrap.token);
    setMessage(`Bootstrap token for ${bootstrap.node} copied.`);
  }

  async function copyBootstrapCommand() {
    if (!bootstrap) return;
    const endpoint = `${window.location.origin}/api/v1${bootstrap.script_path}`;
    const command = `read -rsp 'Ithute bootstrap token: ' ITHUTE_BOOTSTRAP_TOKEN; echo; curl -fsSL -H "X-Ithute-Node-Bootstrap: $ITHUTE_BOOTSTRAP_TOKEN" "${endpoint}" | sudo bash`;
    await navigator.clipboard.writeText(command);
    setMessage(`Safe bootstrap command for ${bootstrap.node} copied. It prompts for the token so the secret is not stored in shell history.`);
  }

  async function activateNode(node: Node) {
    const response = await api(`/platform/hosting/nodes/${node.id}/activate`, { method: "POST" });
    if (!response.ok) { setError(await detail(response, "Node is not ready for activation.")); return; }
    setMessage(`${node.name} passed onboarding and can now receive automatically placed workloads.`);
    await load();
  }

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
      <PageHeader eyebrow="System owner" title="Hosting node agents" description="Secure onboarding, live health, automatic activation, draining and recovery for Ithute hosting capacity. Customer accounts never receive node credentials or Docker-host access." />

      {bootstrap ? <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5"><div className="flex items-start gap-3"><TerminalSquare className="mt-0.5 shrink-0 text-blue-700" size={19}/><div className="min-w-0 flex-1"><h2 className="text-sm font-black text-blue-950">Secure onboarding for {bootstrap.node}</h2><p className="mt-1 text-[10px] leading-5 text-blue-900">Expires {new Date(bootstrap.expires_at).toLocaleString()}. Copy the token, then copy the command and run it on the new VPS. The command prompts for the token so it does not enter shell history.</p><div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]"><code className="min-w-0 break-all rounded-xl border border-blue-200 bg-white p-3 text-[10px]">{bootstrap.token}</code><button className="btn-secondary" onClick={() => void copyBootstrapToken()}><Copy size={13}/>Copy token</button></div><button className="btn-primary mt-3" onClick={() => void copyBootstrapCommand()}><TerminalSquare size={13}/>Copy safe install command</button></div></div></section> : null}

      {newToken ? <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5"><div className="flex items-start gap-3"><ShieldAlert className="mt-0.5 shrink-0 text-amber-700" size={19}/><div className="min-w-0 flex-1"><h2 className="text-sm font-black text-amber-950">Save this credential now — it will not be shown again</h2><p className="mt-1 text-[10px] leading-5 text-amber-900">Install it only in the root-owned configuration for <b>{newToken.node}</b>. Rotating again immediately invalidates this token.</p><div className="mt-3 flex items-center gap-2"><code className="min-w-0 flex-1 break-all rounded-xl border border-amber-200 bg-white p-3 text-[10px] text-[#263a31]">{newToken.token}</code><button className="btn-secondary shrink-0" onClick={() => void copyToken()}><Copy size={13}/>Copy</button></div></div></div></section> : null}

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <section className="surface-card p-4 sm:p-5"><div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black">Registered hosting nodes</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Capacity is configured under Packages & Capacity. Ithute can automatically remove unhealthy nodes from new placement and restore them after sustained recovery.</p></div><button className="icon-button" aria-label="Refresh hosting nodes" disabled={!me?.is_platform_owner} onClick={() => void load()}><RefreshCw size={15}/></button></div>{loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading hosting nodes…</p> : <div className="mt-5 grid gap-4 xl:grid-cols-2">{nodes.map((node) => { const agent = agents[node.id]; return <article key={node.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Server size={18}/></span><div><h3 className="text-sm font-black">{node.name}</h3><p className="mt-0.5 text-[9px] text-[var(--admin-muted)]">{node.hostname}{node.public_ip ? ` · ${node.public_ip}` : ""}</p></div></div><span className={`rounded-full px-2 py-1 text-[9px] font-black ${node.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{node.status}</span></div><div className="mt-4 grid grid-cols-3 gap-2 text-[9px]"><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{gb(node.available.storage_mb)}</b><br/>storage free</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{node.available.memory_mb} MB</b><br/>RAM free</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b>{cpu(node.available.cpu_millicores)}</b><br/>CPU free</div></div><div className="mt-4 rounded-xl border border-[#e4e9e6] p-3"><div className="flex items-center justify-between gap-3"><div><p className="text-[10px] font-black">Node agent</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{agent?.configured ? `Configured · ${agent.token_hint || "credential hidden"}` : "No agent credential yet"}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{agent?.last_seen_at ? `Last seen ${new Date(agent.last_seen_at).toLocaleString()}${agent.agent_version ? ` · ${agent.agent_version}` : ""}` : "No heartbeat received yet"}</p></div><button className="btn-secondary shrink-0" onClick={() => void rotate(node)}><KeyRound size={13}/>{agent?.configured ? "Rotate" : "Create credential"}</button></div></div>
<div className="mt-3 rounded-xl border border-[#e4e9e6] bg-[#f8fbf9] p-3">
  <div className="flex items-center gap-2"><Network size={14}/><p className="text-[10px] font-black">Secure VPS onboarding</p></div>
  <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-[9px] text-emerald-800"><b>Ithute managed private network</b><br/>The installer generates the VPS key locally, Ithute allocates the tunnel IP automatically, and the private key never leaves the VPS.{onboarding[node.id]?.managed_network_ip ? <span className="mt-1 block font-black">Assigned IP: {onboarding[node.id]?.managed_network_ip}</span> : null}</div>
  <input className="input mt-2" value={backupRemotes[node.id] || ""} onChange={(event) => setBackupRemotes((current) => ({ ...current, [node.id]: event.target.value }))} placeholder="Optional rclone backup remote"/>
  <div className="mt-3 flex flex-wrap gap-2"><button className="btn-primary" onClick={() => void createBootstrap(node)}><TerminalSquare size={13}/>Generate secure installer</button>{onboarding[node.id]?.ready && !onboarding[node.id]?.active ? <button className="btn-secondary" onClick={() => void activateNode(node)}><CheckCircle2 size={13}/>Activate now</button> : null}{onboarding[node.id] ? <button className="btn-secondary" onClick={() => void setAutomation(node, !onboarding[node.id]?.automation_enabled)}>{onboarding[node.id]?.automation_enabled ? "Pause automation" : "Enable automation"}</button> : null}</div>
  {onboarding[node.id] ? <>
    <div className={`mt-3 rounded-xl border p-3 text-[9px] ${onboarding[node.id]?.automation_enabled ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
      <b>{onboarding[node.id]?.automation_enabled ? "Automatic self-healing enabled" : "Manual hold"}</b>
      <p className="mt-1">{onboarding[node.id]?.automation_enabled ? `Ithute activates after ${onboarding[node.id]?.thresholds?.auto_activate_seconds ?? 120}s healthy, drains after ${onboarding[node.id]?.thresholds?.auto_drain_seconds ?? 60}s unhealthy, and restores after ${onboarding[node.id]?.thresholds?.auto_recover_seconds ?? 180}s healthy.` : "Ithute will monitor health but will not change this node's scheduling state."}</p>
      {onboarding[node.id]?.last_transition ? <p className="mt-1 font-bold">Last transition: {onboarding[node.id]?.last_transition?.replaceAll("_", " ")}{onboarding[node.id]?.last_transition_at ? ` · ${new Date(onboarding[node.id]?.last_transition_at || "").toLocaleString()}` : ""}</p> : null}
      {onboarding[node.id]?.last_reason ? <p className="mt-1">Reason: {onboarding[node.id]?.last_reason}</p> : null}
    </div>
    <div className="mt-3 grid grid-cols-2 gap-1.5 text-[8px]">{Object.entries(onboarding[node.id].checks).map(([name, passed]) => <span key={name} className={`rounded-lg px-2 py-1.5 font-black ${passed ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{passed ? "✓" : "•"} {name.replaceAll("_", " ")}</span>)}</div>
  </> : null}
</div></article>; })}{!nodes.length ? <p className="text-xs text-[var(--admin-muted)]">No hosting nodes are registered yet. Create sellable capacity from Packages & Capacity first.</p> : null}</div>}</section>
    </div>
  </ControlShell>;
}
