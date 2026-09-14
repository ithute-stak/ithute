import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Github, Mail, MapPin, Phone } from "lucide-react";
import { CvPrintControls } from "./print-button";

export const metadata: Metadata = {
  title: "Koetlisi Theko CV | Ithute Digital Solutions",
  description: "Modern corporate CV for Koetlisi Theko, Founder and Software Engineer at Ithute Digital Solutions.",
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
  "Application Hosting",
  "AI Integrations",
];

const work = [
  {
    title: "LoanHub",
    area: "Financial technology",
    copy: "Production lending and financial-services software supporting real operational workflows at Batlokoa Financial Services in Maseru.",
  },
  {
    title: "Lelefa Debt Collectors",
    area: "Collections technology",
    copy: "Digital collections workflows, reporting and controlled debtor engagement for operational use.",
  },
  {
    title: "Tjekatjeka Holdings",
    area: "Industrial operations",
    copy: "Business-management system work across aluminium and glass, brick production, materials, costs and vehicle operations.",
  },
  {
    title: "Ithute Tutor",
    area: "Education & AI",
    copy: "Online-learning initiative designed to help people understand technology and use AI productively.",
  },
] as const;

const strengths = [
  "Full-stack systems engineering",
  "Business workflow design",
  "Linux server administration",
  "Docker & production deployment",
  "PostgreSQL data architecture",
  "Hosting, DNS & SSL/TLS",
];

export default function FounderCvPage() {
  return (
    <main className="min-h-screen bg-[#e8ecea] px-3 py-6 text-[#17291f] print:bg-white print:px-0 print:py-0">
      <style>{`
        @page { size: A4; margin: 0; }
        @media print {
          html, body { background: white !important; }
          .cv-sheet { width: 210mm !important; min-height: 297mm !important; box-shadow: none !important; }
        }
      `}</style>

      <div className="mx-auto max-w-[210mm] print:max-w-none">
        <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
          <Link href="/founder" className="inline-flex items-center gap-2 text-xs font-black text-[#456359] hover:text-[#123a38]">
            <ArrowLeft size={15} /> Owner profile
          </Link>
          <span className="text-[10px] font-bold uppercase tracking-[.14em] text-[#819087]">Modern Corporate CV</span>
        </div>

        <CvPrintControls />

        <article className="cv-sheet overflow-hidden bg-white shadow-2xl shadow-black/10 print:shadow-none">
          <header className="grid bg-[#0d2d29] text-white sm:grid-cols-[1fr_150px] print:grid-cols-[1fr_150px]">
            <div className="px-8 py-8 print:px-[13mm] print:py-[10mm]">
              <div className="flex items-center gap-3">
                <div className="grid h-12 w-12 place-items-center overflow-hidden rounded-xl bg-white p-1.5">
                  <Image src="/brand/ids-mark.svg" alt="Ithute Digital Solutions" width={42} height={42} priority />
                </div>
                <div>
                  <p className="text-[9px] font-black uppercase tracking-[.18em] text-[#a9c6bb]">Ithute Digital Solutions</p>
                  <p className="mt-1 text-xs font-bold text-white/70">Founder · Software Engineer</p>
                </div>
              </div>

              <h1 className="mt-7 text-[38px] font-black leading-none tracking-[-.05em] sm:text-[46px] print:text-[42px]">Koetlisi Theko</h1>
              <p className="mt-3 max-w-2xl text-sm font-semibold leading-6 text-white/75">
                Full-stack systems · Cloud infrastructure · Linux · Business software
              </p>
              <p className="mt-4 max-w-2xl text-[11px] leading-5 text-white/65">
                Building and operating practical production systems for financial services, industrial operations, education and digital infrastructure.
              </p>
            </div>

            <div className="relative min-h-[190px] bg-[#163c36] sm:min-h-full print:min-h-full">
              <Image
                src="/founder/photo"
                alt="Koetlisi Theko"
                fill
                priority
                sizes="150px"
                className="object-cover object-center"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-[#0d2d29]/35 to-transparent" />
            </div>
          </header>

          <div className="grid sm:grid-cols-[33%_67%] print:grid-cols-[33%_67%]">
            <aside className="bg-[#f3f6f4] px-6 py-7 print:px-[9mm] print:py-[9mm]">
              <section>
                <h2 className="text-[10px] font-black uppercase tracking-[.16em] text-[#315e53]">Contact</h2>
                <div className="mt-4 space-y-3 text-[10px] font-semibold leading-5 text-[#49665d]">
                  <span className="flex items-start gap-2"><MapPin size={13} className="mt-1 shrink-0" /> Maseru, Lesotho</span>
                  <a href="mailto:thekoetlisi@ithute.co.ls" className="flex items-start gap-2 break-all"><Mail size={13} className="mt-1 shrink-0" /> thekoetlisi@ithute.co.ls</a>
                  <a href="tel:+26659001394" className="flex items-start gap-2"><Phone size={13} className="mt-1 shrink-0" /> +266 5900 1394</a>
                  <a href="https://github.com/ithute-stak" className="flex items-start gap-2 break-all"><Github size={13} className="mt-1 shrink-0" /> github.com/ithute-stak</a>
                </div>
              </section>

              <section className="mt-7 border-t border-[#d9e2dd] pt-6">
                <h2 className="text-[10px] font-black uppercase tracking-[.16em] text-[#315e53]">Core strengths</h2>
                <ul className="mt-4 space-y-2.5">
                  {strengths.map((item) => (
                    <li key={item} className="flex gap-2 text-[10px] font-semibold leading-4 text-[#536d64]">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2f7d67]" />
                      {item}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="mt-7 border-t border-[#d9e2dd] pt-6">
                <h2 className="text-[10px] font-black uppercase tracking-[.16em] text-[#315e53]">Technology</h2>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {skills.map((skill) => (
                    <span key={skill} className="rounded-md border border-[#d4dfda] bg-white px-2 py-1 text-[8.5px] font-bold text-[#456359]">
                      {skill}
                    </span>
                  ))}
                </div>
              </section>

              <section className="mt-7 border-t border-[#d9e2dd] pt-6">
                <h2 className="text-[10px] font-black uppercase tracking-[.16em] text-[#315e53]">Education</h2>
                <p className="mt-3 text-[11px] font-black text-[#20342a]">National University of Lesotho</p>
                <p className="mt-1 text-[9.5px] leading-5 text-[#667970]">
                  Studied Computer Science and Mathematics under the Faculty of Science and Technology.
                </p>
              </section>
            </aside>

            <div className="px-7 py-7 print:px-[10mm] print:py-[9mm]">
              <section className="print:break-inside-avoid">
                <h2 className="text-[10px] font-black uppercase tracking-[.17em] text-[#2f6d5d]">Professional profile</h2>
                <div className="mt-2 h-[2px] w-10 bg-[#2f7d67]" />
                <p className="mt-4 text-[10.5px] leading-5.5 text-[#53675e]">
                  Founder and software engineer at Ithute Digital Solutions (IDS). I design, build, deploy and operate digital systems from the business problem through workflow design, frontend and backend engineering, data modelling, Linux deployment and production support. My work combines software development with practical infrastructure knowledge so systems can be built, hosted and maintained as complete operational products.
                </p>
              </section>

              <section className="mt-6">
                <h2 className="text-[10px] font-black uppercase tracking-[.17em] text-[#2f6d5d]">Selected industry work</h2>
                <div className="mt-2 h-[2px] w-10 bg-[#2f7d67]" />
                <div className="mt-4 space-y-4">
                  {work.map((item) => (
                    <article key={item.title} className="print:break-inside-avoid">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h3 className="text-[12px] font-black text-[#17352d]">{item.title}</h3>
                        <span className="text-[8.5px] font-black uppercase tracking-[.12em] text-[#789087]">{item.area}</span>
                      </div>
                      <p className="mt-1.5 text-[9.5px] leading-5 text-[#5d7067]">{item.copy}</p>
                    </article>
                  ))}
                </div>
              </section>

              <section className="mt-6 print:break-inside-avoid">
                <h2 className="text-[10px] font-black uppercase tracking-[.17em] text-[#2f6d5d]">Engineering capability</h2>
                <div className="mt-2 h-[2px] w-10 bg-[#2f7d67]" />
                <div className="mt-4 grid gap-3 sm:grid-cols-2 print:grid-cols-2">
                  <div className="border-l-2 border-[#b8cec5] pl-3">
                    <h3 className="text-[10px] font-black">Application engineering</h3>
                    <p className="mt-1 text-[9px] leading-4.5 text-[#6b7d74]">Next.js interfaces, FastAPI services, REST APIs, dashboards, reporting and operational workflows.</p>
                  </div>
                  <div className="border-l-2 border-[#b8cec5] pl-3">
                    <h3 className="text-[10px] font-black">Data & platforms</h3>
                    <p className="mt-1 text-[9px] leading-4.5 text-[#6b7d74]">PostgreSQL systems, multi-tenant concepts, role-aware applications and production data models.</p>
                  </div>
                  <div className="border-l-2 border-[#b8cec5] pl-3">
                    <h3 className="text-[10px] font-black">Linux & deployment</h3>
                    <p className="mt-1 text-[9px] leading-4.5 text-[#6b7d74]">Docker, reverse proxies, deployment pipelines, service operations and production support.</p>
                  </div>
                  <div className="border-l-2 border-[#b8cec5] pl-3">
                    <h3 className="text-[10px] font-black">Hosting & internet services</h3>
                    <p className="mt-1 text-[9px] leading-4.5 text-[#6b7d74]">Domains, DNS, professional email, application hosting, SSL/TLS and infrastructure operations.</p>
                  </div>
                </div>
              </section>

              <section className="mt-6 border-t border-[#dce4e0] pt-5 print:break-inside-avoid">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between print:flex-row print:items-center print:justify-between">
                  <div>
                    <p className="text-[9px] font-black uppercase tracking-[.15em] text-[#2f6d5d]">Public GitHub portfolio</p>
                    <p className="mt-1 text-[9px] text-[#70827a]">LoanHub · ithute-pay · ithute-tutor · buildtrack-construction · tjekatjeka · gRisk</p>
                  </div>
                  <Image src="/brand/ids-mark.svg" alt="IDS" width={38} height={38} />
                </div>
              </section>
            </div>
          </div>
        </article>
      </div>
    </main>
  );
}
