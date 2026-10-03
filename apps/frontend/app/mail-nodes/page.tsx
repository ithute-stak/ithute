"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, HardDrive, Plus, RefreshCw, Server, ShieldCheck, Wrench, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type MailNode = {
  id: string;
  name: string;
  role: string;
  region: string;
  hostname: string;
  public_ip?: string | null;
  ssh_port: number;
  ssh_user?: string | null;
  storage_path: string;
  capabilities: string[];
  status: "active" | "maintenance" | "disabled";
  healthy: boolean;
  last_heartbeat_at?: string | null;
  total_storage_bytes?: number | null;
  used_storage_bytes?: number | null;
  free_storage_bytes?: number | null;
  agent_version?: string | null;
};

async function api(path: string, init?: RequestInit) {
  const options = {
    credentials: "include" as RequestCredentials,
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

function storage(value?: number | null) {
  if (value === null || value === undefined) return "Awaiting agent";
  if (value >= 1024 ** 4) return `${(value / 1024 ** 4).toFixed(1)} TB`;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

function heartbeat(value?: string | null) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function MailNodesPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [nodes, setNodes] = useState<MailNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [agentToken, setAgentToken] = useState<{node:string;token:string}|null>(null);

  const active = useMemo(() => nodes.filter((node) => node.status === "active").length, [nodes]);
  const healthy = useMemo(() => nodes.filter((node) => node.healthy).length, [nodes]);
  const total = useMemo(() => nodes.reduce((sum, node) => sum + (node.total_storage_bytes || 0), 0), [nodes]);
  const used = useMemo(() => nodes.reduce((sum, node) => sum + (node.used_storage_bytes || 0), 0), [nodes]);

  async function loadNodes() {
    setLoading(true);
    setError("");
    const response = await api("/platform/mail-nodes");
    if (!response.ok) {
      setError(response.status === 403 ? "Platform owner access is required." : "Unable to load mail nodes.");
      setLoading(false);
      return;
    }
    const payload = await response.json();
    setNodes(payload.items || []);
    setLoading(false);
  }

  useEffect(() => {
    void (async () => {
      const response = await api("/auth/me");
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setError("Unable to load account.");
        setLoading(false);
        return;
      }
      const current: Me = await response.json();
      setMe(current);
      if (!current.is_platform_owner) {
        setError("Platform owner access is required.");
        setLoading(false);
        return;
      }
      await loadNodes();
    })();
  }, [router]);

  async function createNode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const capabilities = ["mail", "storage"];
    const response = await api("/platform/mail-nodes", {
      method: "POST",
      body: JSON.stringify({
        name: data.get("name"),
        role: data.get("role"),
        region: data.get("region"),
        hostname: data.get("hostname"),
        public_ip: data.get("public_ip") || null,
        ssh_port: Number(data.get("ssh_port") || 22),
        ssh_user: data.get("ssh_user") || null,
        storage_path: data.get("storage_path") || "/srv/ithute-mail",
        capabilities,
        weight: Number(data.get("weight") || 100),
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "Unable to register mail node.");
      setSaving(false);
      return;
    }
    form.reset();
    setMessage("Mail node registered. Install the Ithute node agent in Phase 3 to begin live heartbeat and capacity reporting.");
    await loadNodes();
    setSaving(false);
  }

  async function updateStatus(node: MailNode, status: MailNode["status"]) {
    setMessage("");
    setError("");
    const response = await api(`/platform/mail-nodes/${node.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "Unable to update mail node.");
      return;
    }
    setMessage(`${node.name} set to ${status}.`);
    await loadNodes();
  }
  async function generateAgentToken(node: MailNode) {
    setMessage("");
    setError("");
    const response = await api(`/platform/mail-nodes/${node.id}/agent-token`, { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "Unable to generate agent credential.");
      return;
    }
    const body = await response.json();
    setAgentToken({ node: node.name, token: body.token });
  }


  return (
    <ControlShell title="Mail nodes" subtitle="Distributed email infrastructure and storage nodes" userEmail={me?.email}>
      <div className="space-y-4">
        <section className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[.12em] text-[#718078]">
                <Server size={14} /> Infrastructure
              </div>
              <h1 className="mt-2 text-2xl font-black tracking-tight text-[#21342a]">Mail node control plane</h1>
              <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[#718078]">
                Register VPS and dedicated mail servers, assign storage capability, monitor agent heartbeat and prepare nodes for mailbox placement.
                SSH metadata is stored for bootstrap planning only; Ithute does not store an SSH password here.
              </p>
            </div>
            <button className="btn-secondary" onClick={() => void loadNodes()} disabled={loading}>
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
          </div>
        </section>

        {error ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] font-semibold text-red-700">
            <AlertTriangle size={15} /> {error}
          </div>
        ) : null}
        {message ? (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[12px] font-semibold text-emerald-700">
            <CheckCircle2 size={15} /> {message}
          </div>
        ) : null}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric icon={Server} label="Registered nodes" value={String(nodes.length)} />
          <Metric icon={Activity} label="Healthy heartbeat" value={`${healthy} / ${active}`} />
          <Metric icon={HardDrive} label="Reported capacity" value={storage(total || null)} />
          <Metric icon={ShieldCheck} label="Reported free" value={storage(total ? Math.max(0, total - used) : null)} />
        </section>

        {me?.is_platform_owner ? (
          <section className="grid gap-4 xl:grid-cols-[390px_1fr]">
            <form onSubmit={createNode} className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm">
              <div className="flex items-center gap-2 font-black text-[#21342a]"><Plus size={15} /> Register VPS / mail node</div>
              <p className="mt-1 text-[10px] leading-4 text-[#819087]">This creates the node record. Agent installation and remote provisioning follow in Phase 3.</p>
              <div className="mt-4 space-y-3">
                <input name="name" className="input" placeholder="Node name, e.g. GlobalIT Mail VPS" required />
                <div className="grid grid-cols-2 gap-2">
                  <select name="role" className="input" defaultValue="combined">
                    <option value="combined">Combined mail</option>
                    <option value="imap">IMAP / storage</option>
                    <option value="smtp">SMTP</option>
                  </select>
                  <input name="region" className="input" defaultValue="lesotho" placeholder="Region" required />
                </div>
                <input name="hostname" className="input" placeholder="mail01.example.com or VPS hostname" required />
                <input name="public_ip" className="input" placeholder="Public IP (optional)" />
                <div className="grid grid-cols-[1fr_110px] gap-2">
                  <input name="ssh_user" className="input" placeholder="SSH user, e.g. root" />
                  <input name="ssh_port" type="number" min="1" max="65535" defaultValue="22" className="input" aria-label="SSH port" />
                </div>
                <input name="storage_path" className="input" defaultValue="/srv/ithute-mail" placeholder="/srv/ithute-mail" required />
                <label className="block">
                  <span className="label">Placement weight</span>
                  <input name="weight" type="number" min="0" max="1000" defaultValue="100" className="input" />
                </label>
                <div className="rounded-xl border border-[#dfe8e3] bg-[#f7faf8] px-3 py-2 text-[10px] leading-4 text-[#66776e]">
                  Credentials are intentionally not stored in this phase. The next phase will bootstrap the Ithute Node Agent and switch normal management to authenticated agent calls.
                </div>
                <button className="btn-primary w-full" disabled={saving}>
                  <Plus size={14} /> {saving ? "Registering..." : "Register node"}
                </button>
              </div>
            </form>

            <div className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-black text-[#21342a]">Infrastructure inventory</p>
                  <p className="text-[10px] text-[#819087]">{nodes.length} registered node{nodes.length === 1 ? "" : "s"}</p>
                </div>
              </div>
              <div className="space-y-3">
                {nodes.map((node) => {
                  const pct = node.total_storage_bytes && node.used_storage_bytes !== null && node.used_storage_bytes !== undefined
                    ? Math.min(100, Math.round((node.used_storage_bytes / node.total_storage_bytes) * 100))
                    : null;
                  return (
                    <article key={node.id} className="rounded-xl border border-[#e2e8e4] p-3.5">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-black text-[#21342a]">{node.name}</p>
                            <span className={`status-badge ${node.healthy ? "status-verified" : node.status === "disabled" ? "status-archived" : "status-suspended"}`}>
                              {node.healthy ? "healthy" : node.status === "active" ? "awaiting heartbeat" : node.status}
                            </span>
                          </div>
                          <p className="mt-1 text-[10px] text-[#718078]">{node.hostname}{node.public_ip ? ` · ${node.public_ip}` : ""} · {node.region}</p>
                          <p className="mt-1 text-[10px] text-[#819087]">Role: {node.role} · Storage: {node.storage_path} · SSH: {node.ssh_user || "not set"}@{node.hostname}:{node.ssh_port}</p>
                          <p className="mt-1 text-[10px] text-[#819087]">Capabilities: {node.capabilities.join(", ") || "none"} · Agent: {node.agent_version || "not connected"}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button className="btn-secondary text-[10px]" onClick={() => void generateAgentToken(node)}>Agent token</button>
                          {node.status !== "active" ? <button className="btn-secondary text-[10px]" onClick={() => void updateStatus(node, "active")}>Activate</button> : null}
                          {node.status !== "maintenance" ? <button className="btn-secondary text-[10px]" onClick={() => void updateStatus(node, "maintenance")}><Wrench size={12} /> Maintenance</button> : null}
                          {node.status !== "disabled" ? <button className="rounded-lg border border-red-200 px-3 py-2 text-[10px] font-bold text-red-700" onClick={() => void updateStatus(node, "disabled")}>Disable</button> : null}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <MiniStat label="Capacity" value={storage(node.total_storage_bytes)} />
                        <MiniStat label="Used" value={storage(node.used_storage_bytes)} />
                        <MiniStat label="Last heartbeat" value={heartbeat(node.last_heartbeat_at)} />
                      </div>
                      {pct !== null ? (
                        <div className="mt-3">
                          <div className="mb-1 flex justify-between text-[9px] font-bold text-[#718078]"><span>Storage usage</span><span>{pct}%</span></div>
                          <div className="h-2 overflow-hidden rounded-full bg-[#edf2ef]"><div className="h-full rounded-full bg-[#285b55]" style={{ width: `${pct}%` }} /></div>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
                {!nodes.length && !loading ? <p className="py-12 text-center text-[11px] text-[#819087]">No mail nodes registered yet.</p> : null}
              </div>
            </div>
          </section>
        ) : null}
        {agentToken ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
            <div className="w-full max-w-xl rounded-2xl bg-white p-5 shadow-2xl">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-black text-[#21342a]">Mail node agent credential</p>
                  <p className="mt-1 text-[11px] text-[#718078]">{agentToken.node}</p>
                </div>
                <button onClick={() => setAgentToken(null)} className="text-xl text-[#718078]">×</button>
              </div>
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] leading-5 text-amber-800">
                This token is shown once. Store it only in <code>/etc/ithute-mail-node/agent.env</code> on the target VPS.
              </div>
              <pre className="mt-3 overflow-x-auto rounded-xl bg-[#123a38] p-4 text-[11px] text-white">{`ITHUTE_MAIL_AGENT_TOKEN=${agentToken.token}`}</pre>
              <div className="mt-4 flex justify-end">
                <button className="btn-primary" onClick={() => setAgentToken(null)}>I have stored it</button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </ControlShell>
  );
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return <div className="rounded-2xl border border-[#e1e7e3] bg-white p-4 shadow-sm"><div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[.08em] text-[#819087]"><Icon size={14} />{label}</div><p className="mt-2 text-xl font-black text-[#21342a]">{value}</p></div>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-[#f7f9f8] px-3 py-2"><p className="text-[8px] font-black uppercase tracking-[.08em] text-[#91a099]">{label}</p><p className="mt-1 truncate text-[10px] font-bold text-[#31443a]">{value}</p></div>;
}
