"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Boxes, Database, Globe2, HardDrive, Mail, Server } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
const money=(value=0)=>"M "+(value/100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const bytes=(value=0)=>value>=1024**3?(value/1024**3).toFixed(1)+" GB":Math.round(value/1024**2)+" MB";
const margin=(bps=0)=>(bps/100).toFixed(1)+"%";

type Environment={
  tenant:{id:string;name:string;slug:string};
  subscription:{status?:string|null;plan_name?:string|null};
  resources:{domains:number;mailboxes:number;hosted_projects:number;databases:number;mailbox_storage_bytes:number;hosting_storage_bytes:number;database_storage_bytes:number;source_storage_bytes:number};
  commercial:{currency:string;recurring_revenue_minor:number;estimated_overage_minor:number;estimated_monthly_revenue_minor:number;allocated_infrastructure_cost_minor:number;gross_profit_minor:number;gross_margin_bps:number};
  servers:{server_id:string;server_name:string;hostname:string;provider?:string|null;allocation_weight:number;allocated_cost_minor:number;cpu_millicores:number;memory_mb:number;storage_mb:number;bandwidth_gb:number;source:string}[];
  overage?:{enabled:boolean;estimated_minor:number;items:{metric:string;units:number;rate_minor:number;amount_minor:number}[]}|null;
  alerts:{severity:string;key:string;message:string}[];
};

export default function CustomerEnvironmentPage({params}:{params:{tenantId:string}}){
  const[data,setData]=useState<Environment|null>(null);const[error,setError]=useState("");
  useEffect(()=>{void(async()=>{const r=await fetch(API+"/platform/commercial/customers/"+params.tenantId,{credentials:"include",cache:"no-store"});const b=await r.json().catch(()=>({}));if(!r.ok)setError(String(b.detail||"Unable to load customer environment."));else setData(b);})();},[params.tenantId]);
  return <ControlShell title={data?.tenant.name||"Customer environment"} subtitle="Services, infrastructure placement, billing and profitability">
    <div className="space-y-5">
      <Link href="/commercial-profitability" className="inline-flex items-center gap-2 text-xs font-black text-[#285b55]"><ArrowLeft size={13}/>Profitability centre</Link>
      {error?<div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-bold text-red-800">{error}</div>:null}
      {data?<><section className="rounded-[28px] bg-[#123a38] p-6 text-white"><p className="text-[9px] font-black uppercase tracking-[.15em] text-[#d8c56a]">Customer environment</p><h1 className="mt-3 text-3xl font-black">{data.tenant.name}</h1><p className="mt-2 text-sm text-white/65">{data.subscription.plan_name||"No package"} · {data.subscription.status||"no subscription"}</p></section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
        ["Estimated MRR",money(data.commercial.estimated_monthly_revenue_minor)],
        ["Infrastructure cost",money(data.commercial.allocated_infrastructure_cost_minor)],
        ["Gross profit",money(data.commercial.gross_profit_minor)],
        ["Gross margin",margin(data.commercial.gross_margin_bps)]
      ].map(([a,b])=><article key={a} className="surface-card p-4"><p className="eyebrow-label">{a}</p><p className="mt-2 text-2xl font-black">{b}</p></article>)}</section>

      <section><div className="mb-3"><p className="eyebrow-label">Services</p><h2 className="mt-1 text-xl font-black">Customer resource footprint</h2></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[[Mail,"Mailboxes",String(data.resources.mailboxes)],[Globe2,"Domains",String(data.resources.domains)],[Server,"Hosted projects",String(data.resources.hosted_projects)],[Database,"Databases",String(data.resources.databases)],[HardDrive,"Mailbox storage",bytes(data.resources.mailbox_storage_bytes)],[HardDrive,"App storage",bytes(data.resources.hosting_storage_bytes)],[Database,"Database storage",bytes(data.resources.database_storage_bytes)],[Boxes,"Source storage",bytes(data.resources.source_storage_bytes)]].map(([Icon,label,value])=><article key={String(label)} className="surface-card p-4"><Icon size={16} className="text-[#285b55]"/><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">{String(label)}</p><p className="mt-1 text-xl font-black">{String(value)}</p></article>)}
      </div></section>

      <section className="surface-card overflow-hidden"><div className="border-b p-5"><p className="eyebrow-label">Infrastructure</p><h2 className="mt-1 text-xl font-black">Where this customer runs</h2></div><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Server</th><th className="p-3">Cost share</th><th className="p-3">Weight</th><th className="p-3">CPU</th><th className="p-3">RAM</th><th className="p-3">Storage</th><th className="p-3">Traffic</th></tr></thead><tbody>{data.servers.length?data.servers.map(row=><tr key={row.server_id} className="border-t"><td className="p-3"><b>{row.server_name}</b><p className="text-[9px] text-[var(--admin-muted)]">{row.hostname}</p></td><td className="p-3 font-black">{money(row.allocated_cost_minor)}</td><td className="p-3">{row.allocation_weight}</td><td className="p-3">{row.cpu_millicores}m</td><td className="p-3">{row.memory_mb} MB</td><td className="p-3">{(row.storage_mb/1024).toFixed(1)} GB</td><td className="p-3">{row.bandwidth_gb} GB</td></tr>):<tr><td colSpan={7} className="p-6 text-center text-[var(--admin-muted)]">No server allocation recorded yet.</td></tr>}</tbody></table></div></section>

      {data.overage?.enabled?<section className="surface-card p-5"><p className="eyebrow-label">Metered usage</p><h2 className="mt-1 text-xl font-black">Estimated extra charge: {money(data.overage.estimated_minor)}</h2><div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{data.overage.items.map(row=><div key={row.metric} className="rounded-xl border p-3 text-xs"><b>{row.metric.replaceAll("_"," ")}</b><p className="mt-1">{row.units} × {money(row.rate_minor)} = {money(row.amount_minor)}</p></div>)}</div></section>:null}

      <section className="surface-card p-5"><p className="eyebrow-label">Alerts</p><div className="mt-3 grid gap-2">{data.alerts.length?data.alerts.map((row,index)=><div key={row.key+String(index)} className={row.severity==="high"?"rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800":"rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"}><b>{row.key.replaceAll("."," ")}</b><p className="mt-1">{row.message}</p></div>):<div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-bold text-emerald-800">No commercial alerts for this customer.</div>}</div></section>
      </>:null}
    </div>
  </ControlShell>;
}
