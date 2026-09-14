import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Cloud,
  Code2,
  Database,
  Download,
  ExternalLink,
  Github,
  GraduationCap,
  Mail,
  MapPin,
  Network,
  Phone,
  Server,
  ShieldCheck,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Koetlisi Theko | Founder of Ithute Digital Solutions",
  description:
    "Meet Koetlisi Theko, founder and software engineer at Ithute Digital Solutions, building practical software, hosting and digital infrastructure in Lesotho.",
  alternates: { canonical: "https://ithute.co.ls/founder" },
  robots: { index: true, follow: true },
};

const skills = [
  "Python",
  "FastAPI",
  "Next.js",
  "TypeScript",
  "React",
  "PostgreSQL",
  "Linux",
  "Docker",
  "GitHub Actions",
  "REST APIs",
  "DNS",
  "Application hosting",
  "AI integrations",
];

const publicRepositories = [
  ["LoanHub", "Financial technology"],
  ["ithute-pay", "Payments technology"],
  ["ithute-tutor", "Education & AI learning"],
  ["buildtrack-construction", "Construction & fleet"],
  ["tjekatjeka", "Industrial operations"],
  ["gRisk", "Risk software experimentation"],
] as const;

const selectedWork = [
  {
    title: "LoanHub",
    eyebrow: "Financial technology",
    description:
      "A lending and financial-services platform developed for real operational use, including work with Batlokoa Financial Services in Maseru.",
    href: "https://loanhub.co.ls",
  },
  {
    title: "Lelefa Debt Collectors",
    eyebrow: "Collections technology",
    description:
      "Digital systems work supporting debt-collection operations, controlled workflows and business reporting.",
    href: "https://lelefadebtcollectors.co.ls",
  },
  {
    title: "Tjekatjeka Holdings",
    eyebrow: "Industrial operations",
    description:
      "Business-management system work for an organisation operating across aluminium and glass, brick production and vehicle operations.",
  },
  {
    title: "Ithute Tutor",
    eyebrow: "Education & AI",
    description:
      "An online-learning initiative designed to help people understand technology and how AI can be used productively.",
  },
];

const capabilities = [
  {
    icon: Code2,
    title: "Full-stack engineering",
    copy: "Modern web interfaces, backend APIs, business workflows, dashboards, reporting and integrations.",
  },
  {
    icon: Database,
    title: "Data & platform design",
    copy: "PostgreSQL-backed applications, operational data models, multi-tenant concepts and role-aware systems.",
  },
  {
    icon: Server,
    title: "Linux & production",
    copy: "Linux servers, Docker, reverse proxies, deployment pipelines, service operations and production support.",
  },
  {
    icon: Network,
    title: "Hosting & internet services",
    copy: "Domains, DNS, professional email, application hosting, SSL/TLS and production infrastructure.",
  },
];

export default function FounderPage() {
  return (
    <main className="min-h-screen bg-[#f4f6f4] text-[#20342a]">
      <section className="relative overflow-hidden bg-[#0c2927] text-white">
        <div className="hero-grid absolute inset-0 opacity-60" />
        <div className="absolute -right-24 top-20 h-96 w-96 rounded-full bg-[#d8c56a]/10 blur-3xl" />
        <div className="relative mx-auto max-w-[1280px] px-5 pb-16 pt-6 sm:px-8 lg:pb-24">
          <header className="flex items-center justify-between gap-4">
            <Link href="/" className="inline-flex items-center gap-2 text-xs font-black text-white/75 transition hover:text-white">
              <ArrowLeft size={15} /> Back to Ithute
            </Link>
            <Link href="/login" className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xs font-extrabold transition hover:bg-white/15">
              Client portal
            </Link>
          </header>

          <div className="grid items-center gap-10 pt-14 lg:grid-cols-[.84fr_1.16fr] lg:pt-20">
            <div className="mx-auto w-full max-w-[430px] lg:mx-0">
              <div className="relative overflow-hidden rounded-[30px] border border-white/10 bg-white/[.06] p-3 shadow-2xl">
                <div className="relative aspect-square overflow-hidden rounded-[24px] bg-[#dbe4df]">
                  <Image
                    src="/founder/photo"
                    alt="Koetlisi Theko, founder of Ithute Digital Solutions"
                    fill
                    priority
                    sizes="(max-width: 1024px) 90vw, 430px"
                    className="object-cover"
                  />
                </div>
                <div className="absolute bottom-6 left-6 rounded-2xl border border-white/10 bg-[#0c2927]/90 px-4 py-3 backdrop-blur">
                  <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#f1de8b]">Founder</p>
                  <p className="mt-1 text-sm font-black">Ithute Digital Solutions</p>
                </div>
              </div>
            </div>

            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[10px] font-black uppercase tracking-[.14em] text-white/65">
                <MapPin size={12} className="text-[#f1de8b]" /> Maseru, Lesotho
              </div>
              <p className="mt-6 text-[10px] font-black uppercase tracking-[.16em] text-[#f1de8b]">Koetlisi Theko</p>
              <h1 className="mt-3 max-w-4xl text-4xl font-black leading-[1.02] tracking-[-.055em] sm:text-6xl">
                Building practical technology for real operations.
              </h1>
              <p className="mt-6 max-w-3xl text-sm leading-7 text-white/65 sm:text-base">
                Founder and software engineer at Ithute Digital Solutions (IDS). I design, build, deploy and operate digital systems across financial services, collections, industrial operations, education and cloud infrastructure.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <a
                  href="/documents/Koetlisi-Theko-CV"
                  download
                  className="inline-flex items-center gap-2 rounded-xl bg-[#f1de8b] px-5 py-3 text-sm font-black text-[#123a38] shadow-lg shadow-black/10"
                >
                  <Download size={16} /> Download CV (PDF)
                </a>
                <a
                  href="https://github.com/ithute-stak"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-5 py-3 text-sm font-black text-white"
                >
                  <Github size={16} /> GitHub
                </a>
              </div>

              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <a href="mailto:thekoetlisi@ithute.co.ls" className="rounded-2xl border border-white/10 bg-white/[.05] p-4 transition hover:bg-white/[.08]">
                  <Mail size={16} className="text-[#f1de8b]" />
                  <p className="mt-3 text-[9px] font-black uppercase tracking-[.13em] text-white/45">Email</p>
                  <p className="mt-1 text-xs font-bold">thekoetlisi@ithute.co.ls</p>
                </a>
                <a href="tel:+26659001394" className="rounded-2xl border border-white/10 bg-white/[.05] p-4 transition hover:bg-white/[.08]">
                  <Phone size={16} className="text-[#f1de8b]" />
                  <p className="mt-3 text-[9px] font-black uppercase tracking-[.13em] text-white/45">Call / WhatsApp</p>
                  <p className="mt-1 text-xs font-bold">+266 5900 1394</p>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-10 lg:grid-cols-[.72fr_1.28fr]">
          <aside className="space-y-5">
            <article className="rounded-[24px] border border-[#dfe6e2] bg-white p-6 shadow-sm">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#edf4f1] text-[#123a38]">
                <GraduationCap size={20} />
              </div>
              <p className="mt-6 text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Education</p>
              <h2 className="mt-2 text-lg font-black tracking-[-.03em]">National University of Lesotho</h2>
              <p className="mt-3 text-xs leading-6 text-[#718078]">
                Studied Computer Science and Mathematics under the Faculty of Science and Technology.
              </p>
            </article>

            <article className="rounded-[24px] border border-[#dfe6e2] bg-white p-6 shadow-sm">
              <p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">Technology</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {skills.map((skill) => (
                  <span key={skill} className="rounded-full border border-[#dfe6e2] bg-[#f8faf8] px-3 py-1.5 text-[10px] font-extrabold text-[#456359]">
                    {skill}
                  </span>
                ))}
              </div>
            </article>

            <article className="rounded-[24px] bg-[#123a38] p-6 text-white shadow-sm">
              <ShieldCheck size={19} className="text-[#f1de8b]" />
              <h2 className="mt-4 text-lg font-black">Engineering principle</h2>
              <p className="mt-3 text-xs leading-6 text-white/60">
                Understand the operation first, then design the software around the real process. Deployment, security and support are part of the product, not afterthoughts.
              </p>
            </article>
          </aside>

          <div>
            <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">What I do</p>
            <h2 className="mt-3 text-3xl font-black tracking-[-.045em] sm:text-4xl">From software idea to running system.</h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-[#718078]">
              My work covers the full path from understanding a business problem to designing the workflow, building the frontend and backend, structuring data, deploying to Linux infrastructure and supporting the system in production.
            </p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              {capabilities.map(({ icon: Icon, title, copy }) => (
                <article key={title} className="rounded-[22px] border border-[#dfe6e2] bg-white p-5 shadow-sm">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#123a38]">
                    <Icon size={18} />
                  </div>
                  <h3 className="mt-4 text-sm font-black">{title}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-[#718078]">{copy}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-[#dfe6e2] bg-white">
        <div className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
          <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">Selected work</p>
          <h2 className="mt-3 text-3xl font-black tracking-[-.045em] sm:text-4xl">Systems connected to real industries.</h2>
          <div className="mt-9 grid gap-4 md:grid-cols-2">
            {selectedWork.map((project) => (
              <article key={project.title} className="rounded-[24px] border border-[#dfe6e2] bg-[#f8faf8] p-6">
                <p className="text-[9px] font-black uppercase tracking-[.14em] text-[#6c8178]">{project.eyebrow}</p>
                <h3 className="mt-3 text-xl font-black tracking-[-.03em]">{project.title}</h3>
                <p className="mt-3 text-xs leading-6 text-[#718078]">{project.description}</p>
                {project.href ? (
                  <a href={project.href} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-2 text-xs font-black text-[#285b55]">
                    Visit project <ExternalLink size={13} />
                  </a>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-9 lg:grid-cols-[.75fr_1.25fr]">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[.15em] text-[#56736a]">GitHub portfolio</p>
            <h2 className="mt-3 text-3xl font-black tracking-[-.045em]">The work is visible in the code.</h2>
            <p className="mt-4 text-sm leading-7 text-[#718078]">
              Current repositories show work across financial technology, hosting infrastructure, education, payments, construction, risk and industrial systems. IDS also maintains private development repositories for internal work.
            </p>
            <a href="https://github.com/ithute-stak" target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#123a38] px-4 py-3 text-xs font-black text-white">
              <Github size={15} /> Open GitHub profile
            </a>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {publicRepositories.map(([repo, description]) => (
              <a
                key={repo}
                href={`https://github.com/ithute-stak/${repo}`}
                target="_blank"
                rel="noreferrer"
                className="group rounded-2xl border border-[#dfe6e2] bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-black text-[#20342a]">{repo}</p>
                    <p className="mt-1 text-[10px] leading-5 text-[#819087]">{description}</p>
                  </div>
                  <ArrowRight size={14} className="mt-1 text-[#91a098] transition group-hover:translate-x-0.5 group-hover:text-[#285b55]" />
                </div>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#123a38] text-white">
        <div className="mx-auto max-w-[1280px] px-5 py-14 sm:px-8 lg:py-20">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2 text-[#f1de8b]">
                <Cloud size={18} />
                <span className="text-[10px] font-black uppercase tracking-[.15em]">Ithute Digital Solutions</span>
              </div>
              <h2 className="mt-4 text-3xl font-black tracking-[-.045em]">Technology built to be used, deployed and operated.</h2>
              <p className="mt-4 text-sm leading-7 text-white/60">
                For business systems, hosting, infrastructure or software-development enquiries, contact IDS directly.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <a href="mailto:thekoetlisi@ithute.co.ls" className="rounded-xl bg-[#f1de8b] px-5 py-3 text-sm font-black text-[#123a38]">Email Koetlisi</a>
              <a href="https://www.facebook.com/koetlisi" target="_blank" rel="noreferrer" className="rounded-xl border border-white/15 bg-white/[.06] px-5 py-3 text-sm font-black">Facebook</a>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
