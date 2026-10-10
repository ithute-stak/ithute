import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, FileCode2, KeyRound, Mail, ShieldCheck } from "lucide-react";
export const metadata: Metadata = { title: "Developer Documentation · Ithute", description: "Documentation for Ithute Auth, Next.js integration, API endpoints, developer signup and security." };
const pages=[
 {name:"Authentication & OAuth",icon:KeyRound,summary:"OAuth 2.0 PKCE, JWKS, registered redirects, online session verification and revocation.",file:"authentication"},
 {name:"Next.js integration",icon:FileCode2,summary:"App Router setup, environment configuration, route handlers and server sessions.",file:"nextjs"},
 {name:"Developer accounts & email",icon:Mail,summary:"Register with your existing email and understand approved Ithute mailbox requests.",file:"accounts-and-mail"},
 {name:"API reference",icon:BookOpen,summary:"Confirmed endpoints, required authentication and access restrictions.",file:"api-reference"},
 {name:"Security & operations",icon:ShieldCheck,summary:"Pre-production security checklist, anti-abuse requirements and operational safeguards.",file:"security"},
];
export default function DeveloperDocs(){
 return <main className="min-h-screen bg-[#07101e] text-slate-100"><div className="mx-3 max-w-none px-6 py-12">
  <Link href="/developer" className="text-sm font-bold text-cyan-300">← Ithute developer portal</Link>
  <p className="mt-16 text-sm font-bold uppercase tracking-[.22em] text-cyan-300">Official technical guides</p>
  <h1 className="mt-3 text-4xl font-black sm:text-5xl">Developer documentation</h1>
  <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-300">Documentation for available Ithute integrations, with security requirements and clear labels for restricted and unfinished services. All technical guides are version-controlled alongside the implementation.</p>
  <div className="mt-12 grid gap-4 md:grid-cols-2">{pages.map(p=><a key={p.file} href={`/developer/docs/${p.file}`} className="group rounded-2xl border border-white/10 bg-white/5 p-6 hover:border-cyan-300/50"><p.icon size={28} className="text-cyan-300"/><h2 className="mt-5 text-xl font-bold">{p.name}</h2><p className="mt-3 text-sm leading-6 text-slate-300">{p.summary}</p><span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-cyan-300">Read guide <ArrowRight size={15}/></span></a>)}</div>
  <section className="mt-12 rounded-2xl border border-cyan-300/20 bg-[#102438] p-7"><h2 className="text-xl font-bold">Important access boundaries</h2><p className="mt-3 leading-7 text-slate-300">Public developer identity registration does not issue API credentials, create mailboxes or grant platform administrator permissions. New OAuth clients and sensitive products require authorized approval. The SDK is distributed from the repository rather than a public npm release.</p><Link href="/developer/register" className="mt-5 inline-flex items-center gap-2 font-bold text-cyan-300">Create an account <ArrowRight size={16}/></Link></section>
 </div></main>;
}
