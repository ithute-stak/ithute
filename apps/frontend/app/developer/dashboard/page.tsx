import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, LockKeyhole, ShieldCheck } from "lucide-react";

export const metadata: Metadata = {
 title: "Developer Workspace · Ithute",
 description: "Protected workspace for managing Ithute developer integrations and access requests.",
};

export default function DeveloperDashboard() {
 return <main className="min-h-screen bg-[#07101e] text-slate-100">
  <div className="mx-auto max-w-4xl px-6 py-16">
   <Link href="/developer" className="text-sm font-bold text-cyan-300">← Developer platform</Link>
   <div className="mt-16 rounded-3xl border border-cyan-400/20 bg-[#102034] p-8 sm:p-12">
    <div className="flex items-center gap-3 text-cyan-300"><LockKeyhole size={28}/><span className="text-sm font-bold uppercase tracking-widest">Protected workspace</span></div>
    <h1 className="mt-6 text-4xl font-black">Your developer workspace</h1>
    <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-300">Ithute's identity-backed developer access requests and administrator approval APIs are being prepared for the dashboard. Until browser-based OAuth sign-in is connected and verified, requests are not available through this page.</p>
    <p className="mt-4 text-slate-300">For your safety, Ithute does not ask you to paste access tokens or API secrets into the browser.</p>
    <div className="mt-8 flex flex-wrap gap-3"><Link href="/developer/auth" className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950">Authentication setup <ArrowRight size={16}/></Link><Link href="/developer/docs" className="inline-flex items-center gap-2 rounded-xl border border-white/20 px-5 py-3 font-bold"><BookOpen size={17}/> Documentation</Link></div>
   </div>
   <p className="mt-8 flex items-start gap-3 text-sm text-slate-400"><ShieldCheck className="shrink-0 text-cyan-300" size={20}/> Application credentials, API grants and mailbox provisioning will remain subject to verified identity, account ownership and approved permissions.</p>
  </div>
 </main>;
}
