"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, BookOpen, LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";

type RequestItem = {id:string;product:string;status:string;created_at:string};
const products = [
  {id:"auth",name:"Ithute Auth & OAuth"},
  {id:"email",name:"Professional email"},
  {id:"dns",name:"DNS & domains"},
  {id:"push",name:"Push integration"},
  {id:"hosting",name:"Hosting"},
];

export default function DeveloperDashboard() {
 const [requests,setRequests]=useState<RequestItem[]>([]);
 const [ready,setReady]=useState(false);
 const [authenticated,setAuthenticated]=useState(false);
 const [busy,setBusy]=useState(false);
 const [product,setProduct]=useState("auth");
 const [justification,setJustification]=useState("");
 const [notice,setNotice]=useState("");
 const load=useCallback(async()=>{
   try {
     const response=await fetch("/api/v1/auth/ithute/developer/requests",{credentials:"include",cache:"no-store"});
     if(response.status===401){setAuthenticated(false);setRequests([]);return;}
     if(!response.ok)throw Error("Unable to load your requests");
     setRequests(await response.json() as RequestItem[]);
     setAuthenticated(true);
   }catch{setNotice("Developer requests are currently unavailable.");}
   finally{setReady(true);}
 },[]);
 useEffect(()=>{void load();},[load]);
 async function submit(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();
  if(justification.trim().length<15){setNotice("Describe your integration in at least 15 characters.");return;}
  setBusy(true);setNotice("");
  try {
   const response=await fetch("/api/v1/auth/ithute/developer/requests",{
    method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({product,justification:justification.trim()}),
   });
   if(!response.ok){setNotice(response.status===403?"Verify your email address before requesting access.":response.status===409?"You already have a pending request for this product.":response.status===429?"Daily request limit reached. Please try again tomorrow.":"Your request could not be submitted.");return;}
   setJustification("");setNotice("Your request has been submitted for review.");await load();
  }catch{setNotice("Cannot reach the developer access service.");}
  finally{setBusy(false);}
 }
 return <main className="min-h-screen bg-[#07101e] text-slate-100"><div className="mx-3 max-w-none px-5 py-12 sm:px-8">
  <div className="flex flex-wrap items-center justify-between gap-4"><Link href="/developer" className="text-sm font-bold text-cyan-300">← Developer portal</Link><Link href="/developer/docs" className="text-sm font-semibold text-cyan-300 hover:text-cyan-100">Read developer guides →</Link></div>
  <div className="mt-12"><span className="text-sm font-bold uppercase tracking-[.18em] text-cyan-300">Developer workspace</span><h1 className="mt-3 text-4xl font-black">My integrations</h1><p className="mt-4 max-w-2xl text-slate-300">Manage service access requests with Ithute Auth. After requesting access, you can read the integration guides while an administrator reviews your request. Approval is a review decision, not automatic service provisioning.</p></div>
  {!ready?<div className="mt-12 text-slate-300">Checking your Ithute Auth session…</div>:!authenticated?<section className="mt-10 rounded-3xl border border-cyan-400/20 bg-[#102034] p-8"><LockKeyhole className="text-cyan-300" size={32}/><h2 className="mt-5 text-2xl font-bold">Sign in with Ithute Auth</h2><p className="mt-3 text-slate-300">Your developer requests are protected by Ithute's central authentication service. No access tokens or passwords are entered on this dashboard.</p><a href="/api/v1/auth/ithute/login?next=%2Fdeveloper%2Fdashboard" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950">Continue with Ithute Auth <ArrowRight size={16}/></a></section>:<div className="mt-10 grid gap-6 lg:grid-cols-2">
   <form onSubmit={submit} className="rounded-2xl border border-white/10 bg-white/5 p-6"><h2 className="text-xl font-bold">Request service access</h2><label className="mt-6 block text-sm font-semibold">Ithute service<select className="mt-2 w-full rounded-xl border border-white/20 bg-[#102034] p-3" value={product} onChange={e=>setProduct(e.target.value)}>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="mt-5 block text-sm font-semibold">Integration description<textarea minLength={15} maxLength={1000} rows={5} required className="mt-2 w-full rounded-xl border border-white/20 bg-[#102034] p-3" value={justification} onChange={e=>setJustification(e.target.value)} placeholder="Describe the application and intended use"/></label><button type="submit" disabled={busy} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 disabled:opacity-50">Submit for review <ArrowRight size={16}/></button></form>
   <section className="rounded-2xl border border-white/10 bg-white/5 p-6"><div className="flex items-center justify-between"><h2 className="text-xl font-bold">Request history</h2><button title="Refresh requests" onClick={()=>void load()} className="rounded-lg border border-white/20 p-2"><RefreshCw size={17}/></button></div><div className="mt-6 space-y-3">{requests.length===0?<p className="text-slate-300">No access requests yet.</p>:requests.map(r=><div key={r.id} className="rounded-xl border border-white/10 p-4"><p className="font-semibold">{products.find(p=>p.id===r.product)?.name??r.product}</p><p className="mt-2 text-sm capitalize text-cyan-300">{r.status}</p><p className="mt-1 text-xs text-slate-400">{new Date(r.created_at).toLocaleString()}</p></div>)}</div></section>
  </div>}
  {notice&&<p role="status" className="mt-6 rounded-xl border border-white/10 p-4 text-sm">{notice}</p>}
  <p className="mt-10 flex items-center gap-2 text-sm text-slate-400"><ShieldCheck size={18}/> Never enter credentials or API tokens into third-party forms. <Link href="/developer/docs" className="inline-flex items-center gap-1 text-cyan-300"><BookOpen size={15}/> Documentation</Link></p>
 </div></main>;
}
