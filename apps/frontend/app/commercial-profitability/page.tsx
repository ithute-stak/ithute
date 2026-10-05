"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, CircleDollarSign, HardDrive, RefreshCw, Server, TrendingUp } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Customer = {
  tenant: { id: string; name: string; slug: string };
  subscription: { status?: string | null; plan_name?: string | null };
  commercial: {
    estimated_monthly_revenue_minor: number;
    allocated_infrastructure_cost_minor: number;
    gross_profit_minor: number;
    gross_margin_bps: number;
  };
  resources: { domains: number; mailboxes: number; hosted_projects: number; databases: number };
};
type ServerRow = {
  server_id: string; name: string; hostname: string; monthly_cost_minor: number; allocated_cost_minor: number;
  allocation_count: number; utilization: Record<string, number | null>;
};
type Portfolio = {
  summary: {
    estimated_mrr_minor: number; allocated_infrastructure_cost_minor: number; total_server_cost_minor: number;
    unallocated_server_cost_minor: number; gross_profit_minor: number; gross_margin_bps: number; alerts: number;
  };
  customers: Customer[];
  servers: ServerRow[];
  alerts: {severity:string;key:string;message:string;tenant_name?:string}[];
};
type Profile = { server_id:string; server_name:string; hostname:string; provider_cost_minor?:number; backup_cost_minor?:number; bandwidth_cost_minor?:number; other_cost_minor?:number; total_cpu_millicores?:number; total_memory_mb?:number; total_storage_mb?:number; included_bandwidth_gb?:number; target_margin_bps?:number };
type Allocation = { id:string;tenant_id:string;tenant_name:string;server_id:string;server_name:string;allocation_weight:number;cpu_millicores:number;memory_mb:number;storage_mb:number;bandwidth_gb:number };

const money = (value=0) => "M " + (value / 100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const margin = (bps=0) => (bps / 100).toFixed(1) + "%";
async function api(path:string, init?:RequestInit){return fetch(API+path,{credentials:"include",cache:"no-store",...init,headers:{"Content-Type":"application/json",...(init?.headers||{})}});}

export default function ProfitabilityCentre(){
  const [portfolio,setPortfolio]=useState<Portfolio|null>(null);
  const [profiles,setProfiles]=useState<Profile[]>([]);
  const [allocations,setAllocations]=useState<Allocation[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [costServer,setCostServer]=useState("");
  const [cost,setCost]=useState({provider:"0",backup:"0",bandwidth:"0",other:"0",cpu:"0",memory:"0",storage:"0",traffic:"0",margin:"30"});
  const [allocation,setAllocation]=useState({tenant:"",server:"",weight:"1",cpu:"0",memory:"0",storage:"0",bandwidth:"0"});

  async function load(){
    setLoading(true);setError("");
    try{
      const [p,c,a]=await Promise.all([api("/platform/commercial/profitability"),api("/platform/commercial/server-costs"),api("/platform/commercial/allocations")]);
      if(!p.ok) throw new Error(p.status===403?"Platform owner access is required.":"Unable to load profitability data.");
      const pb=await p.json(); const cp=c.ok?(await c.json()).items||[]:[]; const ap=a.ok?(await a.json()).items||[]:[];
      setPortfolio(pb);setProfiles(cp);setAllocations(ap);
      if(!allocation.tenant&&pb.customers?.[0]) setAllocation(v=>({...v,tenant:pb.customers[0].tenant.id}));
      if(!allocation.server&&pb.servers?.[0]) setAllocation(v=>({...v,server:pb.servers[0].server_id}));
      if(!costServer&&pb.servers?.[0]) applyProfile(pb.servers[0].server_id,cp);
    }catch(cause){setError(cause instanceof Error?cause.message:"Unable to load profitability data.");}
    finally{setLoading(false);}
  }
  useEffect(()=>{void load();},[]);

  function applyProfile(id:string,rows=profiles){
    setCostServer(id); const row=rows.find(item=>item.server_id===id);
    setCost({
      provider:String((row?.provider_cost_minor||0)/100),backup:String((row?.backup_cost_minor||0)/100),
      bandwidth:String((row?.bandwidth_cost_minor||0)/100),other:String((row?.other_cost_minor||0)/100),
      cpu:String(row?.total_cpu_millicores||0),memory:String(row?.total_memory_mb||0),
      storage:String((row?.total_storage_mb||0)/1024),traffic:String(row?.included_bandwidth_gb||0),
      margin:String((row?.target_margin_bps||3000)/100),
    });
  }

  async function saveCost(event:FormEvent){
    event.preventDefault(); if(!costServer)return; setBusy("cost");setError("");setMessage("");
    const response=await api("/platform/commercial/servers/"+costServer+"/cost-profile",{method:"PUT",body:JSON.stringify({
      currency:"LSL",provider_cost_minor:Math.round(Number(cost.provider)*100),backup_cost_minor:Math.round(Number(cost.backup)*100),
      bandwidth_cost_minor:Math.round(Number(cost.bandwidth)*100),other_cost_minor:Math.round(Number(cost.other)*100),
      total_cpu_millicores:Math.round(Number(cost.cpu)),total_memory_mb:Math.round(Number(cost.memory)),
      total_storage_mb:Math.round(Number(cost.storage)*1024),included_bandwidth_gb:Math.round(Number(cost.traffic)),
      target_margin_bps:Math.round(Number(cost.margin)*100)
    })});
    const body=await response.json().catch(()=>({})); if(!response.ok)setError(String(body.detail||"Unable to save server economics."));
    else{setMessage("Server economics saved. Profitability has been recalculated.");await load();} setBusy("");
  }

  async function saveAllocation(event:FormEvent){
    event.preventDefault(); if(!allocation.tenant||!allocation.server)return; setBusy("allocation");setError("");setMessage("");
    const response=await api("/platform/commercial/customers/"+allocation.tenant+"/servers/"+allocation.server+"/allocation",{method:"PUT",body:JSON.stringify({
      allocation_weight:Math.max(1,Math.round(Number(allocation.weight))),cpu_millicores:Math.max(0,Math.round(Number(allocation.cpu))),
      memory_mb:Math.max(0,Math.round(Number(allocation.memory))),storage_mb:Math.max(0,Math.round(Number(allocation.storage)*1024)),
      bandwidth_gb:Math.max(0,Math.round(Number(allocation.bandwidth))),active:true,source:"manual"
    })});
    const body=await response.json().catch(()=>({})); if(!response.ok)setError(String(body.detail||"Unable to save allocation."));
    else{setMessage("Customer allocation saved. Costs and margins have been recalculated.");await load();} setBusy("");
  }

  return <ControlShell title="Profitability centre" subtitle="Customer environments, server economics and gross margin">
    <div className="space-y-5">
      <section className="rounded-[28px] bg-[#123a38] p-6 text-white">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between"><div>
          <p className="text-[9px] font-black uppercase tracking-[.15em] text-[#d8c56a]">Commercial intelligence</p>
          <h1 className="mt-3 text-3xl font-black">Know what every customer earns and costs.</h1>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-white/65">Subscription revenue, metered usage, infrastructure cost allocation and commercial risk in one workspace.</p>
        </div><button onClick={()=>void load()} disabled={loading} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 text-xs font-black"><RefreshCw size={14}/>{loading?"Loading…":"Refresh"}</button></div>
      </section>
      {message?<div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-bold text-emerald-800">{message}</div>:null}
      {error?<div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-bold text-red-800">{error}</div>:null}

      {portfolio?<><section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {[
          {label:"Estimated MRR",value:money(portfolio.summary.estimated_mrr_minor),icon:CircleDollarSign},
          {label:"Server cost",value:money(portfolio.summary.total_server_cost_minor),icon:Server},
          {label:"Allocated cost",value:money(portfolio.summary.allocated_infrastructure_cost_minor),icon:HardDrive},
          {label:"Gross profit",value:money(portfolio.summary.gross_profit_minor),icon:TrendingUp},
          {label:"Gross margin",value:margin(portfolio.summary.gross_margin_bps),icon:TrendingUp},
          {label:"Alerts",value:String(portfolio.summary.alerts),icon:AlertTriangle},
        ].map(item=>{const Icon=item.icon;return <article key={item.label} className="surface-card p-4"><Icon size={17} className="text-[#285b55]"/><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">{item.label}</p><p className="mt-1 text-xl font-black">{item.value}</p></article>})}
      </section>

      {portfolio.summary.unallocated_server_cost_minor>0?<div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><b>Unallocated server cost: {money(portfolio.summary.unallocated_server_cost_minor)}.</b> Assign customer shares so gross margins include the complete infrastructure cost.</div>:null}

      <section className="surface-card overflow-hidden"><div className="border-b p-5"><p className="eyebrow-label">Customer environments</p><h2 className="mt-1 text-xl font-black">Profitability by customer</h2></div>
        <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Customer</th><th className="p-3">Package</th><th className="p-3">MRR</th><th className="p-3">Cost</th><th className="p-3">Profit</th><th className="p-3">Margin</th><th className="p-3">Resources</th><th className="p-3"/></tr></thead><tbody>
          {portfolio.customers.map(item=><tr key={item.tenant.id} className="border-t"><td className="p-3 font-black">{item.tenant.name}</td><td className="p-3">{item.subscription.plan_name||"No package"}</td><td className="p-3 font-black">{money(item.commercial.estimated_monthly_revenue_minor)}</td><td className="p-3">{money(item.commercial.allocated_infrastructure_cost_minor)}</td><td className="p-3 font-black">{money(item.commercial.gross_profit_minor)}</td><td className={item.commercial.gross_margin_bps<2000?"p-3 font-black text-red-700":"p-3 font-black text-emerald-700"}>{margin(item.commercial.gross_margin_bps)}</td><td className="p-3 text-[10px]">{item.resources.mailboxes} mail · {item.resources.hosted_projects} apps · {item.resources.databases} DBs</td><td className="p-3"><Link href={"/commercial-profitability/customers/"+item.tenant.id} className="font-black text-[#285b55]">Open →</Link></td></tr>)}
        </tbody></table></div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <form onSubmit={saveCost} className="surface-card p-5"><p className="eyebrow-label">Infrastructure economics</p><h2 className="mt-1 text-xl font-black">Server cost & capacity</h2>
          <select value={costServer} onChange={e=>applyProfile(e.target.value)} className="input mt-4 w-full">{profiles.map(row=><option key={row.server_id} value={row.server_id}>{row.server_name} · {row.hostname}</option>)}</select>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[
            ["provider","Provider / month (M)"],["backup","Backup / month (M)"],["bandwidth","Bandwidth / month (M)"],["other","Other / month (M)"],
            ["cpu","CPU capacity (millicores)"],["memory","RAM capacity (MB)"],["storage","Storage capacity (GB)"],["traffic","Included traffic (GB)"],["margin","Target margin (%)"]
          ].map(([key,label])=><label key={key} className="text-[9px] font-black uppercase text-[var(--admin-muted)]">{label}<input className="input mt-1 w-full" type="number" min="0" step="0.01" value={cost[key as keyof typeof cost]} onChange={e=>setCost(v=>({...v,[key]:e.target.value}))}/></label>)}</div>
          <button className="btn-primary mt-4" disabled={!costServer||busy==="cost"}>{busy==="cost"?"Saving…":"Save server economics"}</button>
        </form>

        <form onSubmit={saveAllocation} className="surface-card p-5"><p className="eyebrow-label">Cost allocation</p><h2 className="mt-1 text-xl font-black">Assign customer capacity</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><select value={allocation.tenant} onChange={e=>setAllocation(v=>({...v,tenant:e.target.value}))} className="input">{portfolio.customers.map(row=><option key={row.tenant.id} value={row.tenant.id}>{row.tenant.name}</option>)}</select><select value={allocation.server} onChange={e=>setAllocation(v=>({...v,server:e.target.value}))} className="input">{portfolio.servers.map(row=><option key={row.server_id} value={row.server_id}>{row.name}</option>)}</select></div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">{[["weight","Cost weight"],["cpu","CPU millicores"],["memory","RAM MB"],["storage","Storage GB"],["bandwidth","Traffic GB"]].map(([key,label])=><label key={key} className="text-[9px] font-black uppercase text-[var(--admin-muted)]">{label}<input className="input mt-1 w-full" type="number" min={key==="weight"?"1":"0"} value={allocation[key as keyof typeof allocation]} onChange={e=>setAllocation(v=>({...v,[key]:e.target.value}))}/></label>)}</div>
          <button className="btn-primary mt-4" disabled={!allocation.tenant||!allocation.server||busy==="allocation"}>{busy==="allocation"?"Saving…":"Save customer allocation"}</button>
        </form>
      </section>

      <section className="surface-card overflow-hidden"><div className="border-b p-5"><p className="eyebrow-label">Fleet economics</p><h2 className="mt-1 text-xl font-black">Server cost & capacity</h2></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Server</th><th className="p-3">Cost</th><th className="p-3">Allocated</th><th className="p-3">Customers</th><th className="p-3">CPU</th><th className="p-3">RAM</th><th className="p-3">Storage</th></tr></thead><tbody>{portfolio.servers.map(row=><tr key={row.server_id} className="border-t"><td className="p-3"><b>{row.name}</b><p className="text-[9px] text-[var(--admin-muted)]">{row.hostname}</p></td><td className="p-3 font-black">{money(row.monthly_cost_minor)}</td><td className="p-3">{money(row.allocated_cost_minor)}</td><td className="p-3">{row.allocation_count}</td><td className="p-3">{row.utilization.cpu_millicores==null?"—":String(row.utilization.cpu_millicores)+"%"}</td><td className="p-3">{row.utilization.memory_mb==null?"—":String(row.utilization.memory_mb)+"%"}</td><td className="p-3">{row.utilization.storage_mb==null?"—":String(row.utilization.storage_mb)+"%"}</td></tr>)}</tbody></table></div></section>

      <section className="surface-card p-5"><p className="eyebrow-label">Commercial alerts</p><h2 className="mt-1 text-xl font-black">What needs attention</h2><div className="mt-4 grid gap-2">{portfolio.alerts.length?portfolio.alerts.slice(0,40).map((row,index)=><div key={row.key+String(index)} className={row.severity==="high"?"rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800":"rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"}><b>{row.tenant_name||row.key}</b><p className="mt-1">{row.message}</p></div>):<div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-bold text-emerald-800">No commercial alerts.</div>}</div></section>

      {allocations.length?<section className="surface-card p-5"><p className="eyebrow-label">Allocation ledger</p><div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{allocations.map(row=><div key={row.id} className="rounded-xl border p-3"><b className="text-sm">{row.tenant_name}</b><p className="text-[10px] text-[var(--admin-muted)]">{row.server_name} · weight {row.allocation_weight}</p><p className="mt-1 text-[10px]">{(row.storage_mb/1024).toFixed(1)} GB · {row.memory_mb} MB RAM · {row.cpu_millicores}m CPU</p></div>)}</div></section>:null}
      </>:null}
    </div>
  </ControlShell>;
}
