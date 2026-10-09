"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Clock3, KeyRound, ShieldCheck } from "lucide-react";

type AccessRequest = { id:string;product:string;status:string;created_at:string };
type Product = "auth"|"email"|"dns"|"push"|"hosting";
const PRODUCTS: {id:Product;name:string}[]=[
 {id:"auth",name:"Ithute Auth / OAuth"},
 {id:"email",name:"Professional email"},
 {id:"dns",name:"DNS and domains"},
 {id:"push",name:"Push integrations"},
 {id:"hosting",name:"Hosting and operations"}
];

export default function DeveloperDashboard(){
 const [token,setToken]=useState("");
 const [requests,setRequests]=useState<AccessRequest[]>([]);
 const [product,setProduct]=useState<Product>("auth");
 const [justification,setJustification]=useState("");
 const [message,setMessage]=useState("");
 const [busy,setBusy]=useState(false);
 const apiBase=process.env.NEXT_PUBLIC_ITHUTE_AUTH_ISSUER;
 async function load(accessToken:string){
   if(!apiBase){setMessage("Developer API connection is not configured.");return;}
   const res=await fetch(new URL("/v1/account/developer/access-requests",apiBase),{
     headers:{Authorization:`Bearer ${accessToken}`},cache:"no-store"
   });
   if(!res.ok){setMessage("Your session could not be verified. Sign in again.");return;}
   setRequests(await res.json() as AccessRequest[]);
 }
 useEffect(()=>{const saved=sessionStorage.getItem("ithute_developer_access_token");if(saved){setToken(saved);void load(saved)}},[]);
 async function connect(){
  const value=token.trim();
  if(!value){setMessage("Enter your Ithute Auth access token.");return;}
  sessionStorage.setItem("ithute_developer_access_token",value);
  await load(value);
 }
 async function submit(){
  if(!apiBase||!token||justification.trim().length<15){setMessage("Sign in and provide at least 15 characters describing your integration.");return;}
  setBusy(true);setMessage("");
  try{
   const response=await fetch(new URL("/v1/account/developer/access-requests",apiBase),{
     method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},
     body:JSON.stringify({product,justification:justification.trim()}),
   });
   if(!response.ok){setMessage(response.status===409?"You already have a pending request for this service.":"Unable to submit request.");return;}
   setJustification("");setMessage("Request submitted for administrator review.");await load(token);
  }catch{setMessage("Service is unavailable. Please try again.");}finally{setBusy(false)}
 }
 return <main className="min-h-screen bg-[#07101e] text-white"><div className="mx-auto max-w-5xl px-6 py-12">
   <Link href="/developer" className="text-sm font-bold text-cyan-300">← Developer portal</Link>
   <div className="mt-12 flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-bold uppercase tracking-[.18em] text-cyan-300">Developer workspace</p><h1 className="mt-3 text-4xl font-black">My integrations</h1><p className="mt-3 max-w-2xl text-slate-300">Request access to Ithute products and follow the review process. Access requests do not issue credentials automatically.</p></div><ShieldCheck className="text-cyan-300" size={36}/></div>
   <section className="mt-10 rounded-2xl border border-white/10 bg-white/5 p-6"><h2 className="text-xl font-bold">Connect your Ithute identity</h2><p className="mt-2 text-sm text-slate-300">Temporary integration interface: supply an Ithute Auth access token. A dedicated OAuth sign-in flow will replace this step.</p><div className="mt-4 flex flex-wrap gap-3"><input aria-label="Ithute Auth access token" type="password" value={token} onChange={e=>setToken(e.target.value)} placeholder="Ithute Auth access token" className="min-w-0 flex-1 rounded-xl border border-white/20 bg-[#0b1b2e] p-3"/><button onClick={()=>void connect()} className="rounded-xl bg-cyan-400 px-6 py-3 font-bold text-slate-950">Connect</button><button onClick={()=>{sessionStorage.removeItem("ithute_developer_access_token");setToken("");setRequests([]);}} className="rounded-xl border border-white/20 px-4 py-3">Disconnect</button></div></section>
   <div className="mt-6 grid gap-6 lg:grid-cols-2"><section className="rounded-2xl border border-white/10 bg-white/5 p-6"><h2 className="flex items-center gap-2 text-xl font-bold"><KeyRound className="text-cyan-300"/> Request access</h2><label className="mt-6 block text-sm font-bold">Product<select value={product} onChange={e=>setProduct(e.target.value as Product)} className="mt-2 w-full rounded-xl border border-white/20 bg-[#0b1b2e] p-3">{PRODUCTS.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="mt-4 block text-sm font-bold">How will you use this integration?<textarea minLength={15} maxLength={1000} rows={5} value={justification} onChange={e=>setJustification(e.target.value)} className="mt-2 w-full rounded-xl border border-white/20 bg-[#0b1b2e] p-3" placeholder="Describe your application and its intended users"/></label><button disabled={busy||!token} onClick={()=>void submit()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 disabled:opacity-50">Submit request <ArrowRight size={16}/></button></section>
   <section className="rounded-2xl border border-white/10 bg-white/5 p-6"><h2 className="text-xl font-bold">My requests</h2><div className="mt-6 space-y-3">{requests.length===0?<p className="text-sm text-slate-300">No requests to display yet.</p>:requests.map(r=><div key={r.id} className="rounded-xl border border-white/10 p-4"><div className="flex items-center justify-between gap-2"><strong>{PRODUCTS.find(p=>p.id===r.product)?.name??r.product}</strong><span className="flex items-center gap-1 text-xs text-cyan-300">{r.status==="approved"?<CheckCircle2 size={14}/>:<Clock3 size={14}/>} {r.status}</span></div><p className="mt-2 text-xs text-slate-400">{new Date(r.created_at).toLocaleDateString()}</p></div>)}</div></section></div>
   {message&&<p role="status" className="mt-6 rounded-xl border border-white/10 p-4 text-sm">{message}</p>}
   <p className="mt-12 text-sm text-slate-400">Need integration instructions? <Link href="/developer/docs" className="text-cyan-300 underline">Read developer documentation</Link>.</p>
 </div></main>;
}
