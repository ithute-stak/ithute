"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Eye, EyeOff, History, RefreshCw, ShieldCheck, ShoppingBag } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type LifecycleState = "sellable" | "hidden" | "legacy" | "archived";
type PlanLifecycle = {
  id: string;
  code: string;
  name: string;
  state: LifecycleState;
  customer_visible: boolean;
  is_active: boolean;
  subscriber_count: number;
  retired_at?: string | null;
};

const stateMeta: Record<LifecycleState, {label:string;copy:string;icon:typeof ShoppingBag}> = {
  sellable: {label:"Sellable", copy:"Visible to new customers and available for plan changes.", icon:ShoppingBag},
  hidden: {label:"Hidden", copy:"Active internally but not shown in the public catalogue.", icon:EyeOff},
  legacy: {label:"Legacy", copy:"Kept for existing subscribers but closed to new sales.", icon:History},
  archived: {label:"Archived", copy:"Inactive and retained only for historical records.", icon:Archive},
};

export default function PackageLifecyclePage(){
  const [items,setItems]=useState<PlanLifecycle[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const response=await fetch(`${API}/platform/commercial/package-lifecycle`,{credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(response.status===403?"Platform owner access is required.":"Unable to load package lifecycle.");
      setItems((await response.json()).items||[]);
    }catch(cause){setError(cause instanceof Error?cause.message:"Unable to load package lifecycle.")}finally{setLoading(false)}
  },[]);
  useEffect(()=>{void load()},[load]);

  async function change(item:PlanLifecycle,state:LifecycleState){
    setBusy(item.id);setError("");setMessage("");
    try{
      const response=await fetch(`${API}/platform/commercial/package-lifecycle/${item.id}`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({state})});
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(typeof body.detail==="string"?body.detail:"Unable to change package state.");
      setMessage(`${item.name} is now ${state}.`);await load();
    }catch(cause){setError(cause instanceof Error?cause.message:"Unable to change package state.")}finally{setBusy("")}
  }

  const counts=useMemo(()=>items.reduce((acc,item)=>{acc[item.state]=(acc[item.state]||0)+1;return acc},{sellable:0,hidden:0,legacy:0,archived:0} as Record<LifecycleState,number>),[items]);

  return <ControlShell title="Package lifecycle" subtitle="Keep one clean sales catalogue while preserving existing customer contracts safely.">
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-[28px] bg-[#123a38] p-6 text-white shadow-[0_22px_60px_rgba(18,58,56,.18)] sm:p-7">
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between"><div><div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[9px] font-black uppercase tracking-[.13em] text-[#d8c56a]"><ShieldCheck size={13}/> Catalogue safety</div><h1 className="mt-4 text-3xl font-black tracking-[-.045em]">No more package conflicts.</h1><p className="mt-3 max-w-3xl text-sm leading-7 text-white/65">Sellable plans are the only plans offered to new customers. Legacy plans remain active only for tenants already depending on them. A subscribed plan cannot be archived.</p></div><button onClick={()=>void load()} disabled={loading} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 text-xs font-black"><RefreshCw size={14} className={loading?"animate-spin":""}/>Refresh</button></div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{(Object.keys(stateMeta) as LifecycleState[]).map(state=>{const meta=stateMeta[state];const Icon=meta.icon;return <article key={state} className="rounded-2xl border border-[#dfe7e2] bg-white p-4"><div className="flex items-center justify-between"><div className="grid h-9 w-9 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Icon size={16}/></div><span className="text-2xl font-black text-[#20342a]">{counts[state]}</span></div><h2 className="mt-3 text-sm font-black">{meta.label}</h2><p className="mt-1 text-[10px] leading-5 text-[#718078]">{meta.copy}</p></article>})}</section>

      {message?<div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-bold text-emerald-800">{message}</div>:null}
      {error?<div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-bold text-red-700">{error}</div>:null}

      <section className="space-y-3">{items.map(item=>{const meta=stateMeta[item.state];return <article key={item.id} className="rounded-[22px] border border-[#dfe7e2] bg-white p-5 shadow-sm"><div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between"><div><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#edf4f1] px-2.5 py-1 text-[9px] font-black uppercase text-[#285b55]">{item.code}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[9px] font-black uppercase text-slate-700">{meta.label}</span>{item.subscriber_count>0?<span className="rounded-full bg-amber-50 px-2.5 py-1 text-[9px] font-black uppercase text-amber-700">{item.subscriber_count} subscriber{item.subscriber_count===1?"":"s"}</span>:null}</div><h2 className="mt-2 text-lg font-black text-[#20342a]">{item.name}</h2><p className="mt-1 text-[11px] text-[#718078]">{meta.copy}</p></div><div className="flex flex-wrap gap-2">{(["sellable","hidden","legacy","archived"] as LifecycleState[]).filter(state=>state!==item.state).map(state=><button key={state} disabled={busy===item.id||(state==="archived"&&item.subscriber_count>0)} onClick={()=>void change(item,state)} className="rounded-xl border border-[#dce5e0] px-3 py-2 text-[10px] font-black text-[#285b55] disabled:cursor-not-allowed disabled:opacity-40">{state==="sellable"?"Make sellable":state==="hidden"?"Hide":state==="legacy"?"Mark legacy":"Archive"}</button>)}</div></div></article>})}</section>
      {!loading&&!items.length?<div className="rounded-2xl border border-dashed border-[#d8e1dc] bg-white p-8 text-center text-sm text-[#718078]">No packages found.</div>:null}
    </div>
  </ControlShell>;
}
