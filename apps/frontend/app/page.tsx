import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Cloud,
  GraduationCap,
  Landmark,
  Layers3,
  Mail,
  Network,
  Server,
  ShieldCheck,
  Store,
  WalletCards,
} from "lucide-react";

export const metadata: Metadata = {
  title: "!thute · Digital systems built for real operations",
  description:
    "!thute is a Lesotho technology hub building multi-tenant platforms for finance, collections, commerce, construction, education, email, DNS and cloud operations.",
  applicationName: "!thute",
  keywords: [
    "Ithute",
    "Lesotho software",
    "business systems",
    "school management",
    "loan management",
    "POS",
    "email hosting",
    "DNS hosting",
  ],
  robots: { index: true, follow: true },
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23123a38'/%3E%3Ctext x='32' y='43' font-size='34' text-anchor='middle' fill='%23f1de8b' font-family='Arial' font-weight='800'%3E!%3C/text%3E%3C/svg%3E",
  },
};

const solutions = [
  {
    icon: Mail,
    eyebrow: "Cloud infrastructure",
    title: "!thute Mail & DNS",
    description:
      "Professional business email, authoritative DNS, DNSSEC, Webmail, transactional email, reseller hosting, domain services, monitoring and recovery in one platform.",
    tags: ["Email", "DNS", "Domains", "Hosting"],
    href: "/pricing",
    action: "Explore Mail & DNS",
  },
  {
    icon: Landmark,
    eyebrow: "Financial technology",
    title: "LoanHub",
    description:
      "A multi-company lending platform for borrower profiles, loan operations, credit workflows, company controls and shared financial-service infrastructure.",
    tags: ["Lending", "Borrowers", "Credit", "Multi-tenant"],
  },
  {
    icon: WalletCards,
    eyebrow: "Collections technology",
    title: "Lelefa Collections",
    description:
      "Operational software for debt portfolios, debtor engagement, collector activity, reporting and controlled collection workflows.",
    tags: ["Collections", "Portfolios", "Engagement", "Reporting"],
  },
  {
    icon: Store,
    eyebrow: "Commerce technology",
    title: "!thute POS",
    description:
      "A scalable multi-tenant point-of-sale and business operations platform designed for retailers, wholesalers and growing commercial organisations.",
    tags: ["POS", "Inventory", "Sales", "Multi-branch"],
  },
  {
    icon: Building2,
    eyebrow: "Construction technology",
    title: "!thute Construction",
    description:
      "A connected operating system for tenders, projects, sites, employees, payroll, fleet, fuel, maintenance, costs and progress reporting.",
    tags: ["Projects", "Tenders", "Fleet", "Workforce"],
  },
  {
    icon: GraduationCap,
    eyebrow: "Education technology · Coming next",
    title: "!thute Schools",
    description:
      "A multi-tenant school management system for institutions of different sizes, with one platform for administration, learning operations and parent/student services.",
    tags: ["Schools", "Students", "Fees", "Academics"],
  },
];

const foundations = [
  {
    icon: Layers3,
    title: "Multi-tenant by design",
    copy: "Build once, serve many organisations safely, with organisation-level data, roles, plans and operational boundaries.",
  },
  {
    icon: ShieldCheck,
    title: "Security as infrastructure",
    copy: "Identity, permissions, auditability, encrypted transport, controlled access and production-safe operational practices are part of the platform layer.",
  },
  {
    icon: Network,
    title: "Connected systems",
    copy: "APIs, integrations and shared platform services let !thute products work as an ecosystem instead of isolated applications.",
  },
  {
    icon: Server,
    title: "Production operations",
    copy: "Deployment, monitoring, backups, health checks and service operations are treated as product capabilities, not afterthoughts.",
  },
];

const schoolCapabilities = [
  "Admissions & student records",
  "Attendance & discipline",
  "Fees, billing & receipts",
  "Classes, subjects & timetables",
  "Exams, marks & report cards",
  "Teachers, staff & payroll",
  "Parent & student portals",
  "Multi-campus administration",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#f4f6f4] text-[#20342a]">
      <section className="relative overflow-hidden bg-[#0c2927] text-white">
        <div className="hero-grid absolute inset-0 opacity-70" />
        <div className="absolute -right-28 top-28 h-96 w-96 rounded-full bg-[#d8c56a]/10 blur-3xl" />
        <div className="absolute -left-32 bottom-0 h-80 w-80 rounded-full bg-emerald-300/10 blur-3xl" />

        <div className="relative mx-auto max-w-[1280px] px-5 pb-20 pt-6 sm:px-8 lg:pb-28">
          <header className="flex items-center justify-between gap-4">
            <Link href="/" className="flex items-center gap-3" aria-label="!thute home">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#f1de8b] text-2xl font-black text-[#123a38] shadow-lg shadow-black/10">
                !
              </div>
              <div>
                <p className="text-lg font-black tracking-[-.04em]">thute</p>
                <p className="text-[9px] font-bold uppercase tracking-[.2em] text-white/45">Digital solutions hub</p>
              </div>
            </Link>

            <nav className="flex items-center gap-2 sm:gap-4">
              <a href="#solutions" className="hidden text-xs font-bold text-white/65 transition hover:text-white md:inline">
                Solutions
              </a>
              <a href="#platform" className="hidden text-xs font-bold text-white/65 transition hover:text-white md:inline">
                Platform
              </a>
              <a href="#schools" className="hidden text-xs font-bold text-white/65 transition hover:text-white md:inline">
                Schools
              </a>
              <Link href="/docs" className="hidden text-xs font-bold text-white/65 transition hover:text-white lg:inline">
                Mail & DNS docs
              </Link>
              <a
                href="https://panel.ithute.co.ls/login"
                className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xs font-extrabold transition hover:bg-white/15"
              >
                Client portal
              </a>
            </nav>
          </header>

          <div className="grid items-center gap-12 pt-20 lg:grid-cols-[1.08fr_.92fr] lg:pt-28">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[10px] font-black uppercase tracking-[.14em] text-white/65">
                <span className="live-dot is-live" />
                Technology built in Lesotho · Built for real operations
              </div>

              <h1 className="mt-6 max-w-4xl text-4xl font-black leading-[1.02] tracking-[-.055em] sm:text-6xl lg:text-7xl">
                One home for the systems that move organisations forward.
              </h1>
              <p className="mt-6 max-w-2xl text-sm leading-7 text-white/65 sm:text-base">
                !thute is becoming a technology hub for business, finance, commerce, construction, education and cloud infrastructure. We build connected, multi-tenant solutions that turn real operational problems into dependable digital systems.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <a
                  href="#solutions"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#f1de8b] px-5 py-3 text-sm font-black text-[#123a38] shadow-lg shadow-black/10"
                >
                  Explore our solutions <ArrowRight size={16} />
                </a>
                <Link
                  href="/pricing"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-5 py-3 text-sm font-black text-white"
                >
                  <Cloud size={16} /> Mail & DNS
                </Link>
              </div>

              <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-[11px] font-bold text-white/50">
                {["Multi-tenant platforms", "Production infrastructure", "Industry-focused systems"].map((item) => (
                  <span key={item} className="inline-flex items-center gap-2">
                    <CheckCircle2 size={14} className="text-[#f1de8b]" /> {item}
                  </span>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="rounded-[30px] border border-white/10 bg-white/[.07] p-4 shadow-2xl backdrop-blur sm:p-5">
                <div className="rounded-[22px] border border-white/5 bg-[#f7f9f8] p-5 text-[#20342a] sm:p-6">
                  <div className="flex items-start justify-between gap-5">
                    <div>
                      <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#718078]">The !thute ecosystem</p>
                      <p className="mt-2 max-w-sm text-xl font-black tracking-[-.035em]">Different industries. One engineering foundation.</p>
                    </div>
                    <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#123a38] text-xl font-black text-[#f1de8b]">!</div>
                  </div>

                  <div className="mt-6 grid gap-3 sm:grid-cols-2">
                    {[
                      [Mail, "Mail & DNS", "Cloud infrastructure"],
                      [Landmark, "LoanHub", "Financial services"],
                      [Store, "POS", "Commerce"],
                      [Building2, "Construction", "Projects & fleet"],
                      [WalletCards, "Collections", "Debt operations"],
                      [GraduationCap, "Schools", "Education · next"],
                    ].map(([Icon, title, subtitle]) => {
                      const IconComponent = Icon as typeof Mail;
                      return (
                        <div key={String(title)} className="flex items-center gap-3 rounded-2xl border border-[#e1e7e3] bg-white p-3.5">
                          <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#edf4f1] text-[#123a38]">
                            <IconComponent size={16} />
                          </div>
                          <div>
                            <p className="text-xs font-black">{String(title)}</p>
                            <p className="mt-0.5 text-[9px] font-semibold text-[#819087]">{String(subtitle)}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-4 rounded-2xl bg-[#123a38] p-4 text-white">
                    <p className="text-[9px] font-black uppercase tracking-[.14em] text-[#f1de8b]">Our direction</p>
                    <p className="mt-2 text-xs font-bold leading-5 text-white/80">
                      Shared identity, billing, APIs, operations and infrastructure can eventually connect !thute products into one digital ecosystem.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-[#e0e6e2] bg-white">
        <div className="mx-auto grid max-w-[1280px] gap-4 px-5 py-5 text-center sm:grid-cols-3 sm:px-8">
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">One technology hub</p>
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Multiple industry platforms</p>
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Built to grow together</p>
        </div>
      </section>

      <section id="solutions" className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">The !thute portfolio</p>
            <h2 className="mt-3 text-3xl font-black tracking-[-.045em] sm:text-4xl">Solutions for the work organisations actually do.</h2>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#718078]">
              Our projects are not isolated experiments. They form a growing portfolio of operational platforms, each focused on a real industry while sharing the same commitment to secure, practical and scalable software.
            </p>
          </div>
          <div className="rounded-2xl border border-[#dde5e0] bg-white px-4 py-3 text-xs font-bold text-[#56736a] shadow-sm">
            New solutions can join the same !thute ecosystem as the portfolio grows.
          </div>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {solutions.map(({ icon: Icon, eyebrow, title, description, tags, href, action }) => (
            <article key={title} className="group flex min-h-[310px] flex-col rounded-[24px] border border-[#dfe6e2] bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-xl hover:shadow-[#123a38]/5">
              <div className="flex items-start justify-between gap-4">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#edf4f1] text-[#123a38] transition group-hover:bg-[#123a38] group-hover:text-[#f1de8b]">
                  <Icon size={19} />
                </div>
                <span className="rounded-full bg-[#f4f6f4] px-3 py-1.5 text-[9px] font-black uppercase tracking-[.12em] text-[#718078]">{eyebrow}</span>
              </div>
              <h3 className="mt-6 text-xl font-black tracking-[-.035em]">{title}</h3>
              <p className="mt-3 text-xs leading-6 text-[#718078]">{description}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <span key={tag} className="rounded-full border border-[#e0e7e3] px-2.5 py-1 text-[9px] font-bold text-[#56736a]">{tag}</span>
                ))}
              </div>
              <div className="mt-auto pt-6">
                {href && action ? (
                  <Link href={href} className="inline-flex items-center gap-2 text-xs font-black text-[#285b55]">
                    {action} <ArrowRight size={14} />
                  </Link>
                ) : (
                  <span className="text-[10px] font-black uppercase tracking-[.12em] text-[#9aa59f]">Part of !thute</span>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section id="platform" className="bg-[#123a38] text-white">
        <div className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
          <div className="grid gap-10 lg:grid-cols-[.9fr_1.1fr] lg:items-end">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#f1de8b]">Shared foundation</p>
              <h2 className="mt-3 text-3xl font-black tracking-[-.045em] sm:text-4xl">A hub should be more than a collection of logos.</h2>
              <p className="mt-4 max-w-xl text-sm leading-7 text-white/60">
                The long-term value of !thute is a common platform layer: secure identity, organisations, subscriptions, APIs, infrastructure and operations that can support many specialised products without rebuilding the basics every time.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {foundations.map(({ icon: Icon, title, copy }) => (
                <article key={title} className="rounded-2xl border border-white/10 bg-white/[.06] p-5">
                  <Icon size={18} className="text-[#f1de8b]" />
                  <h3 className="mt-4 text-sm font-black">{title}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-white/55">{copy}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="schools" className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
        <div className="overflow-hidden rounded-[30px] border border-[#dfe6e2] bg-white shadow-sm">
          <div className="grid lg:grid-cols-[.92fr_1.08fr]">
            <div className="bg-[#efe4a4] p-7 sm:p-10 lg:p-12">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#123a38] text-[#f1de8b]">
                <GraduationCap size={22} />
              </div>
              <p className="mt-8 text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">Coming next</p>
              <h2 className="mt-3 text-3xl font-black tracking-[-.045em] text-[#123a38] sm:text-4xl">!thute Schools</h2>
              <p className="mt-4 max-w-lg text-sm leading-7 text-[#52685e]">
                A multi-tenant school management platform that can serve individual schools, school groups and multiple campuses from one secure system while keeping each institution's data and operations properly separated.
              </p>
            </div>
            <div className="p-7 sm:p-10 lg:p-12">
              <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#718078]">Planned operating areas</p>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                {schoolCapabilities.map((item) => (
                  <div key={item} className="flex items-center gap-3 rounded-xl border border-[#e1e7e3] bg-[#f8faf8] px-4 py-3">
                    <CheckCircle2 size={15} className="shrink-0 text-[#2f6d63]" />
                    <span className="text-xs font-bold text-[#42584e]">{item}</span>
                  </div>
                ))}
              </div>
              <p className="mt-6 text-xs leading-6 text-[#819087]">
                The school platform will be designed as a true !thute product—not a one-school custom application—so packages, institutions, campuses, users and permissions can scale commercially.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-[#dfe6e2] bg-white">
        <div className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-20">
          <div className="grid gap-8 lg:grid-cols-[.8fr_1.2fr] lg:items-center">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">Why !thute</p>
              <h2 className="mt-3 text-3xl font-black tracking-[-.045em]">Local understanding. Production ambition.</h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                ["01", "Operational first", "We start from how organisations actually work, then design the system around the process."],
                ["02", "Built to scale", "Multi-tenant architecture and shared platform services let solutions grow beyond one customer."],
                ["03", "One ecosystem", "Over time, !thute products can share identity, infrastructure, integrations and operational intelligence."],
              ].map(([n, title, copy]) => (
                <article key={n} className="rounded-2xl bg-[#f4f6f4] p-5">
                  <p className="text-[10px] font-black text-[#9aa59f]">{n}</p>
                  <h3 className="mt-4 text-sm font-black">{title}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-[#718078]">{copy}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
        <div className="relative overflow-hidden rounded-[30px] bg-[#0c2927] px-7 py-10 text-white sm:px-10 lg:px-12 lg:py-14">
          <div className="hero-grid absolute inset-0 opacity-40" />
          <div className="relative flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#f1de8b]">The hub is only beginning</p>
              <h2 className="mt-3 text-3xl font-black tracking-[-.045em] sm:text-4xl">Build one strong !thute brand around every solution.</h2>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-white/60">
                Finance, education, construction, commerce and cloud infrastructure can live under one trusted technology identity while each product keeps its specialist workflows.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <a href="#solutions" className="inline-flex items-center gap-2 rounded-xl bg-[#f1de8b] px-5 py-3 text-sm font-black text-[#123a38]">
                View solutions <ArrowRight size={16} />
              </a>
              <a href="https://panel.ithute.co.ls/login" className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-5 py-3 text-sm font-black">
                Open client portal
              </a>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-[#dfe6e2] bg-white">
        <div className="mx-auto grid max-w-[1280px] gap-8 px-5 py-9 sm:px-8 md:grid-cols-[1.2fr_.8fr] md:items-end">
          <div>
            <Link href="/" className="inline-flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#123a38] text-lg font-black text-[#f1de8b]">!</div>
              <div>
                <p className="font-black tracking-[-.03em]">thute</p>
                <p className="text-[9px] font-bold uppercase tracking-[.15em] text-[#8b9891]">Digital solutions hub</p>
              </div>
            </Link>
            <p className="mt-4 max-w-xl text-[11px] leading-5 text-[#819087]">
              Building practical digital platforms for organisations in Lesotho and beyond.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-3 text-[10px] font-bold text-[#718078] md:justify-end">
            <Link href="/pricing">Mail & DNS pricing</Link>
            <Link href="/docs">Documentation</Link>
            <Link href="/service-status">Service status</Link>
            <Link href="/legal">Policies</Link>
            <a href="https://panel.ithute.co.ls/login">Client portal</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
