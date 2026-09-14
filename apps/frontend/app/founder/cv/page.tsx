import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Github, Mail, MapPin, Phone } from "lucide-react";
import { CvPrintControls } from "./print-button";

export const metadata: Metadata = {
  title: "Koetlisi Theko CV | Ithute Digital Solutions",
  description: "Print-ready CV for Koetlisi Theko, Founder and Software Engineer at Ithute Digital Solutions.",
  robots: { index: false, follow: false },
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

const projects = [
  ["LoanHub", "Financial technology", "Lending and financial-services software developed for real operational use."],
  ["Lelefa Debt Collectors", "Collections technology", "Digital workflows supporting debt-collection operations, reporting and controlled engagement."],
  ["Tjekatjeka Holdings", "Industrial operations", "Business-management system work across aluminium and glass, brick production and vehicle operations."],
  ["Ithute Tutor", "Education & AI", "Online-learning initiative focused on technology understanding and practical AI use."],
] as const;

const capabilities = [
  ["Full-stack engineering", "Modern web interfaces, backend APIs, workflows, dashboards, reporting and integrations."],
  ["Data & platform design", "PostgreSQL-backed systems, operational data models, multi-tenant concepts and role-aware applications."],
  ["Linux & production", "Linux servers, Docker, reverse proxies, deployment pipelines, service operations and production support."],
  ["Hosting & internet services", "Domains, DNS, professional email, application hosting, SSL/TLS and production infrastructure."],
] as const;

const repositories = ["LoanHub", "ithute-pay", "ithute-tutor", "buildtrack-construction", "tjekatjeka", "gRisk"];

export default function FounderCvPage() {
  return (
    <main className="min-h-screen bg-[#edf1ef] px-3 py-6 text-[#20342a] print:bg-white print:px-0 print:py-0">
      <style>{`@page { size: A4; margin: 0; } @media print { html, body { background: white !important; } }`}</style>

      <div className="mx-auto max-w-[210mm] print:max-w-none">
        <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
          <Link href="/founder" className="inline-flex items-center gap-2 text-xs font-black text-[#456359] hover:text-[#123a38]">
            <ArrowLeft size={15} /> Owner profile
          </Link>
          <span className="text-[10px] font-bold uppercase tracking-[.14em] text-[#819087]">Print-ready CV</span>
        </div>

        <CvPrintControls />

        <article className="bg-white p-6 shadow-xl shadow-black/5 sm:p-10 print:min-h-[297mm] print:p-[13mm] print:shadow-none">
          <header className="border-b-2 border-[#123a38] pb-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <div className="grid h-12 w-12 place-items-center overflow-hidden rounded-xl border border-[#dfe6e2] bg-white">
                    <Image src="/brand/ids-mark.svg" alt="Ithute Digital Solutions" width={42} height={42} priority />
                  </div>
                  <div>
                    <p className="text-[9px] font-black uppercase tracking-[.18em] text-[#56736a]">Ithute Digital Solutions</p>
                    <p className="mt-1 text-xs font-bold text-[#718078]">Founder · Software Engineer</p>
                  </div>
                </div>
                <h1 className="mt-5 text-4xl font-black tracking-[-.045em] text-[#123a38]">Koetlisi Theko</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f7168]">
                  Founder and software engineer building practical digital systems, production infrastructure and connected business platforms in Lesotho.
                </p>
              </div>

              <div className="grid gap-2 text-[11px] font-semibold text-[#456359] sm:text-right">
                <span className="inline-flex items-center gap-2 sm:justify-end"><MapPin size={13} /> Maseru, Lesotho</span>
                <a href="mailto:thekoetlisi@ithute.co.ls" className="inline-flex items-center gap-2 sm:justify-end"><Mail size={13} /> thekoetlisi@ithute.co.ls</a>
                <a href="tel:+26659001394" className="inline-flex items-center gap-2 sm:justify-end"><Phone size={13} /> +266 5900 1394</a>
                <a href="https://github.com/ithute-stak" className="inline-flex items-center gap-2 sm:justify-end"><Github size={13} /> github.com/ithute-stak</a>
              </div>
            </div>
          </header>

          <section className="mt-7 print:break-inside-avoid">
            <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Professional profile</p>
            <p className="mt-3 text-[12px] leading-6 text-[#53675e]">
              I design, build, deploy and operate digital systems across financial services, collections, industrial operations, education and cloud infrastructure. My work covers the full path from understanding the business problem to workflow design, frontend and backend engineering, data modelling, Linux deployment and production support.
            </p>
          </section>

          <section className="mt-7 print:break-inside-avoid">
            <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Core capabilities</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 print:grid-cols-2">
              {capabilities.map(([title, copy]) => (
                <div key={title} className="rounded-xl border border-[#dfe6e2] p-4 print:rounded-none">
                  <h2 className="text-[12px] font-black text-[#20342a]">{title}</h2>
                  <p className="mt-1.5 text-[10px] leading-5 text-[#718078]">{copy}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-7 print:break-inside-avoid">
            <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Education</p>
            <h2 className="mt-2 text-sm font-black text-[#20342a]">National University of Lesotho</h2>
            <p className="mt-1 text-[11px] leading-5 text-[#718078]">
              Studied Computer Science and Mathematics under the Faculty of Science and Technology.
            </p>
          </section>

          <section className="mt-7">
            <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Selected work</p>
            <div className="mt-3 space-y-3">
              {projects.map(([title, area, description]) => (
                <div key={title} className="grid gap-1 border-b border-[#e5ebe7] pb-3 last:border-0 print:break-inside-avoid sm:grid-cols-[150px_1fr] print:grid-cols-[145px_1fr]">
                  <div>
                    <h2 className="text-[12px] font-black text-[#20342a]">{title}</h2>
                    <p className="mt-0.5 text-[9px] font-bold uppercase tracking-[.1em] text-[#718078]">{area}</p>
                  </div>
                  <p className="text-[10px] leading-5 text-[#5f7168]">{description}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-7 grid gap-6 sm:grid-cols-2 print:grid-cols-2">
            <div className="print:break-inside-avoid">
              <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Technology</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {skills.map((skill) => (
                  <span key={skill} className="rounded-full border border-[#dfe6e2] px-2.5 py-1 text-[9px] font-bold text-[#456359] print:rounded-none">
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            <div className="print:break-inside-avoid">
              <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#56736a]">Public GitHub portfolio</p>
              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
                {repositories.map((repo) => (
                  <span key={repo} className="text-[10px] font-bold text-[#456359]">{repo}</span>
                ))}
              </div>
            </div>
          </section>

          <footer className="mt-8 border-t border-[#dfe6e2] pt-4 text-[9px] leading-4 text-[#819087] print:mt-6">
            Ithute Digital Solutions · Maseru, Lesotho · Practical software, hosting and digital infrastructure for real operations.
          </footer>
        </article>
      </div>
    </main>
  );
}
