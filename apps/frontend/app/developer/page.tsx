import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Code2, Fingerprint, Globe2, KeyRound, Mail, ServerCog, ShieldCheck, Webhook } from "lucide-react";

export const metadata: Metadata = {
  title: "Developer Platform · Ithute",
  description: "Discover the Ithute developer platform: central authentication, Next.js SDK, email, DNS, hosting and integration onboarding.",
  alternates: { canonical: "https://ithute.co.ls/developer" },
};

const integrations = [
  { name: "Ithute Auth", icon: Fingerprint, status: "Available", detail: "Central identity, OAuth 2.0 authorization code + PKCE, signed tokens, MFA and session verification.", action: "Set up authentication", href: "/developer/auth" },
  { name: "Next.js Auth SDK", icon: Code2, status: "SDK preview", detail: "Server-only App Router integration: PKCE, callbacks, encrypted sessions and central logout.", action: "Read SDK docs", href: "/developer/docs/nextjs" },
  { name: "Professional Email", icon: Mail, status: "Managed service", detail: "Mailbox services for organizations, SMTP/IMAP infrastructure and webmail. Access and provisioning are subject to approval.", action: "Read mail documentation", href: "/developer/docs/accounts-and-mail" },
  { name: "DNS & Domains", icon: Globe2, status: "Managed service", detail: "Authoritative DNS, domain operations and DNSSEC tools for accounts with appropriate permissions.", action: "Read access requirements", href: "/developer/docs/api-reference" },
  { name: "Platform Operations", icon: ServerCog, status: "Restricted", detail: "Hosting, infrastructure health and service administration for authorized tenants.", action: "Sign in", href: "/login" },
  { name: "Push & Integrations", icon: Webhook, status: "Restricted", detail: "Application push endpoints and integrations managed through the elevated Ithute platform dashboard.", action: "Read API access policy", href: "/developer/docs/api-reference" },
];

export default function DeveloperPage() {
  return <main className="min-h-screen bg-[#07101e] text-slate-100">
    <div className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(ellipse_at_70%_5%,rgba(14,165,233,.17),transparent_60%)]" />
    <div className="relative mx-3 max-w-none px-5 pb-24 pt-8 sm:px-8">
      <header className="flex flex-wrap items-center justify-between gap-5 border-b border-white/10 pb-6">
        <Link href="/" className="text-xl font-black tracking-tight">!thute <span className="font-medium text-cyan-300">/ developer</span></Link>
        <nav aria-label="Developer navigation" className="flex flex-wrap gap-5 text-sm text-slate-300">
          <a href="#products" className="hover:text-white">Products</a><Link href="/developer/docs" className="hover:text-white">Documentation</Link>
          <a href="#start" className="hover:text-white">Get started</a>
          <Link href="/login" className="hover:text-white">Sign in</Link>
        </nav>
      </header>
      <section className="grid items-center gap-12 py-20 lg:grid-cols-[1.2fr_.8fr]">
        <div><p className="mb-5 text-xs font-bold uppercase tracking-[.24em] text-cyan-300">Ithute developer platform</p>
          <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-6xl">Build with Ithute.<br/><span className="text-cyan-300">One identity. Connected services.</span></h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">Discover developer-facing capabilities, connect Next.js applications to Ithute Auth, and start with an existing email address. Managed email, DNS and infrastructure products are available according to your organization's access.</p>
          <div className="mt-9 flex flex-wrap gap-3"><Link href="/developer/register" className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 hover:bg-cyan-300">Create developer account <ArrowRight size={17}/></Link><a href="#products" className="rounded-xl border border-white/20 px-6 py-3 font-semibold hover:bg-white/10">Explore integrations</a></div>
        </div>
        <div className="rounded-3xl border border-cyan-400/20 bg-[#0b1b2e] p-7 shadow-2xl shadow-cyan-900/10"><div className="mb-6 flex items-center gap-2 text-sm font-semibold text-cyan-300"><ShieldCheck size={18}/> Secure by design</div><pre className="overflow-auto text-sm leading-8 text-slate-200"><code>{`// Next.js App Router
import { createIthuteAuth }
  from "ithute-auth";

const auth = createIthuteAuth({
  issuer: process.env.ITHUTE_AUTH_ISSUER!,
  clientId: process.env.ITHUTE_AUTH_CLIENT_ID!,
  callbackUrl: process.env.ITHUTE_AUTH_CALLBACK_URL!,
  secret: process.env.ITHUTE_AUTH_SESSION_SECRET!,
});`}</code></pre><p className="mt-5 text-xs text-slate-400">Server-only configuration. SDK package publishing is pending. Integration instructions are available in Ithute developer documentation.</p></div>
      </section>
      <section id="products" className="scroll-mt-12"><div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-bold text-cyan-300">Capabilities</p><h2 className="mt-2 text-3xl font-black">Explore developer products</h2></div><p className="max-w-md text-sm text-slate-400">Public documentation and restricted services are clearly distinguished.</p></div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{integrations.map((item)=><article key={item.name} className="flex flex-col rounded-2xl border border-white/10 bg-white/[.04] p-6 transition hover:border-cyan-300/40 hover:bg-white/[.07]"><div className="mb-5 flex items-center justify-between"><span className="rounded-xl bg-cyan-400/10 p-3 text-cyan-300"><item.icon size={23}/></span><span className="text-xs font-semibold text-slate-400">{item.status}</span></div><h3 className="text-xl font-bold">{item.name}</h3><p className="mt-3 flex-1 text-sm leading-6 text-slate-300">{item.detail}</p><Link href={item.href} className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-cyan-300 hover:text-cyan-100">{item.action}<ArrowRight size={15}/></Link></article>)}</div>
      </section>
      <section id="start" className="mt-20 grid gap-6 rounded-3xl border border-white/10 bg-[#0d2032] p-7 lg:grid-cols-2 lg:p-12"><div><BookOpen className="mb-5 text-cyan-300" size={30}/><h2 className="text-3xl font-black">Start building</h2><p className="mt-4 leading-7 text-slate-300">Register with your current email address, then request application access. OAuth application registration and callback management are currently performed by authorized platform administrators.</p><Link href="/developer/register" className="mt-6 inline-flex items-center gap-2 font-bold text-cyan-300">Register with an existing email <ArrowRight size={17}/></Link></div><div><KeyRound className="mb-5 text-cyan-300" size={30}/><h2 className="text-3xl font-black">Prefer @ithute.co.ls?</h2><p className="mt-4 leading-7 text-slate-300">You can request an Ithute email mailbox. Availability, identity verification and mailbox provisioning must be approved separately; creating an Auth account does not automatically create a mailbox.</p><a href="mailto:support@ithute.co.ls?subject=Ithute%20developer%20mailbox%20request" className="mt-6 inline-flex items-center gap-2 font-bold text-cyan-300">Request an Ithute mailbox <ArrowRight size={17}/></a></div></section>
      <footer className="mt-16 flex flex-wrap justify-between gap-4 border-t border-white/10 pt-7 text-sm text-slate-400"><span>© Ithute Digital Solutions · Developer platform</span><span>Secure identity · Managed integrations · Lesotho</span></footer>
    </div></main>;
}
