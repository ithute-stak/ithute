import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Github, Mail, MapPin, Phone } from "lucide-react";
import { CvPrintControls } from "./print-button";

export const metadata: Metadata = {
  title: "Koetlisi Theko CV | Ithute Digital Solutions",
  description: "Professional CV for Koetlisi Theko, Founder and Software Engineer at Ithute Digital Solutions.",
  robots: { index: false, follow: false },
};

const technologies = [
  "Python / FastAPI",
  "Next.js / TypeScript",
  "React",
  "PostgreSQL",
  "Linux",
  "Docker",
  "Git / GitHub Actions",
  "REST APIs",
  "DNS & Hosting",
  "AI Integrations",
];

const focus = [
  "Business systems",
  "Cloud & server operations",
  "Application hosting",
  "Database-backed platforms",
  "Automation & APIs",
  "AI-assisted products",
];

const strengths = [
  "Operational problem solving",
  "End-to-end delivery",
  "Production deployment",
  "Multi-tenant thinking",
  "Security-aware design",
  "Support & maintainability",
];

const experience = [
  "Design and develop business systems from operational requirements through production deployment.",
  "Build Next.js/TypeScript frontends, Python/FastAPI services and PostgreSQL-backed workflows.",
  "Operate Linux and Docker hosting environments, reverse proxies, domains, DNS, SSL/TLS and CI/CD.",
  "Develop multi-tenant controls, authentication, reporting, integrations and production support practices.",
];

const projects = [
  {
    title: "LoanHub",
    area: "Financial technology",
    href: "https://loanhub.co.ls",
    copy: "Production lending platform used in operational financial-services workflows, including work with Batlokoa Financial Services in Maseru.",
  },
  {
    title: "Lelefa Debt Collectors",
    area: "Collections technology",
    href: "https://lelefadebtcollectors.co.ls",
    copy: "Software supporting debt-collection operations, controlled workflows and business reporting.",
  },
  {
    title: "Tjekatjeka Holdings",
    area: "Industrial operations",
    copy: "Business-management system work spanning aluminium/glass, brick production and vehicle operations.",
  },
  {
    title: "Ithute Tutor",
    area: "Education & AI",
    copy: "Online learning initiative focused on technology and practical use of artificial intelligence.",
  },
];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 border-b border-[#dce4e9] pb-1">
      <h2 className="text-[12px] font-black uppercase tracking-[-.01em] text-[#0a63b8] print:text-[11px]">
        {children}
      </h2>
    </div>
  );
}

function BulletList({ items, compact = false }: { items: string[]; compact?: boolean }) {
  return (
    <ul className={compact ? "space-y-1" : "space-y-1.5"}>
      {items.map((item) => (
        <li key={item} className="grid grid-cols-[8px_1fr] gap-2 text-[10px] leading-[1.35] text-[#253746] print:text-[9px]">
          <span className="mt-[5px] h-1.5 w-1.5 rounded-full bg-[#35a543]" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default function FounderCvPage() {
  return (
    <main className="min-h-screen bg-[#e9eef1] px-3 py-6 text-[#253746] print:bg-white print:px-0 print:py-0">
      <style>{`
        @page { size: A4; margin: 0; }
        @media print {
          html, body { background: #fff !important; }
          * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        }
      `}</style>

      <div className="mx-auto w-full max-w-[210mm]">
        <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
          <Link href="/founder" className="inline-flex items-center gap-2 text-xs font-black text-[#456359] hover:text-[#0d2d4a]">
            <ArrowLeft size={15} /> Owner profile
          </Link>
          <span className="text-[10px] font-bold uppercase tracking-[.14em] text-[#819087]">Professional CV</span>
        </div>

        <CvPrintControls />

        <article className="mx-auto min-h-[297mm] overflow-hidden bg-white shadow-2xl shadow-black/10 print:h-[297mm] print:min-h-0 print:w-[210mm] print:shadow-none">
          <header className="relative bg-[#0d2d4a] px-[13mm] pb-[8mm] pt-[10mm] text-white">
            <div className="absolute inset-x-0 bottom-0 h-[3px] bg-[#35a543]" />
            <div className="grid grid-cols-[31mm_1fr] items-center gap-[8mm]">
              <div className="relative h-[31mm] w-[31mm] overflow-hidden rounded-[3mm] border border-white/10 bg-white/5">
                <Image
                  src="/founder/photo"
                  alt="Koetlisi Theko"
                  fill
                  priority
                  sizes="117px"
                  className="object-cover"
                />
              </div>

              <div>
                <h1 className="text-[28px] font-black leading-none tracking-[.01em] print:text-[26px]">KOETLISI THEKO</h1>
                <p className="mt-3 text-[13px] font-black text-[#d6b35a] print:text-[12px]">
                  Founder &amp; Software Engineer - Ithute Digital Solutions (IDS)
                </p>
                <p className="mt-3 text-[10px] font-medium text-[#c8d6e2] print:text-[9px]">
                  Full-stack systems&nbsp;&nbsp;|&nbsp;&nbsp;Linux &amp; cloud infrastructure&nbsp;&nbsp;|&nbsp;&nbsp;Hosting&nbsp;&nbsp;|&nbsp;&nbsp;AI-enabled products
                </p>

                <div className="mt-4 grid max-w-[126mm] grid-cols-2 gap-x-8 gap-y-2 text-[9px] font-medium text-[#d9e4ec] print:text-[8.5px]">
                  <span className="inline-flex items-center gap-2"><MapPin size={12} /> Maseru, Lesotho</span>
                  <a href="mailto:thekoetlisi@ithute.co.ls" className="inline-flex items-center gap-2"><Mail size={12} /> thekoetlisi@ithute.co.ls</a>
                  <a href="tel:+26659001394" className="inline-flex items-center gap-2"><Phone size={12} /> (+266) 5900 1394</a>
                  <a href="https://github.com/ithute-stak" className="inline-flex items-center gap-2"><Github size={12} /> github.com/ithute-stak</a>
                </div>
              </div>
            </div>
          </header>

          <div className="grid grid-cols-[1fr_58mm] gap-[7mm] px-[13mm] pb-[11mm] pt-[7mm]">
            <section className="pr-[1mm]">
              <SectionTitle>Professional Profile</SectionTitle>
              <p className="text-[10px] leading-[1.45] text-[#253746] print:text-[9.2px]">
                Founder and software engineer building production systems for finance, collections, industrial operations,
                education and digital infrastructure. Experienced across the full delivery cycle: discovery, UI, APIs,
                PostgreSQL data models, Linux deployment, Docker, DNS, hosting and operational support.
              </p>

              <div className="mt-4">
                <SectionTitle>Experience</SectionTitle>
                <div className="flex items-baseline justify-between gap-4">
                  <h3 className="text-[11px] font-black text-[#253746] print:text-[10px]">Founder &amp; Software Engineer</h3>
                  <span className="text-[9px] font-black text-[#0a63b8] print:text-[8.5px]">Ithute Digital Solutions</span>
                </div>
                <p className="mt-1 text-[8.5px] font-medium text-[#637789] print:text-[8px]">
                  Maseru, Lesotho&nbsp;&nbsp;|&nbsp;&nbsp;Product engineering, hosting and infrastructure
                </p>
                <div className="mt-2">
                  <BulletList items={experience} />
                </div>
              </div>

              <div className="mt-4">
                <SectionTitle>Selected Production &amp; Industry Work</SectionTitle>
                <div className="space-y-2.5">
                  {projects.map((project) => (
                    <article key={project.title} className="break-inside-avoid">
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-[10px] font-black text-[#253746] print:text-[9.3px]">{project.title}</h3>
                        {project.href ? (
                          <a href={project.href} className="text-[7.5px] font-medium text-[#0a63b8] print:text-[7px]">
                            {project.href.replace("https://", "")}
                          </a>
                        ) : null}
                      </div>
                      <p className="mt-0.5 text-[7.5px] font-black uppercase tracking-[.02em] text-[#637789] print:text-[7px]">
                        {project.area}
                      </p>
                      <p className="mt-0.5 text-[8.7px] leading-[1.35] text-[#253746] print:text-[8.1px]">{project.copy}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <aside className="border-l border-[#dce4e9] pl-[5mm]">
              <SectionTitle>Core Technologies</SectionTitle>
              <div className="space-y-1.5">
                {technologies.map((item) => (
                  <div key={item} className="rounded-[4px] bg-[#f2f4f5] px-2.5 py-1.5 text-[8.5px] font-black text-[#253746] print:text-[8px]">
                    {item}
                  </div>
                ))}
              </div>

              <div className="mt-4">
                <SectionTitle>Education</SectionTitle>
                <h3 className="text-[9.5px] font-black text-[#253746] print:text-[9px]">National University of Lesotho</h3>
                <p className="mt-0.5 text-[8px] font-medium text-[#637789]">Faculty of Science &amp; Technology</p>
                <p className="mt-1 text-[8.5px] leading-[1.35] text-[#253746] print:text-[8px]">
                  Studied Computer Science and Mathematics.
                </p>
              </div>

              <div className="mt-4">
                <SectionTitle>Professional Focus</SectionTitle>
                <BulletList items={focus} compact />
              </div>

              <div className="mt-4">
                <SectionTitle>Engineering Strengths</SectionTitle>
                <BulletList items={strengths} compact />
              </div>

              <div className="mt-4">
                <SectionTitle>Links</SectionTitle>
                <div className="space-y-3 text-[8px] leading-[1.35] text-[#253746]">
                  <div>
                    <p className="font-black uppercase text-[#637789]">GitHub</p>
                    <p>github.com/ithute-stak</p>
                  </div>
                  <div>
                    <p className="font-black uppercase text-[#637789]">IDS</p>
                    <p>ithute.co.ls</p>
                  </div>
                  <div>
                    <p className="font-black uppercase text-[#637789]">Email</p>
                    <p>thekoetlisi@ithute.co.ls</p>
                  </div>
                </div>
              </div>
            </aside>
          </div>

          <footer className="mx-[13mm] mt-auto flex items-center justify-between border-t border-[#dce4e9] py-[4mm] text-[7px] font-medium text-[#637789]">
            <span>Koetlisi Theko - Curriculum Vitae</span>
            <span>Ithute Digital Solutions | Maseru, Lesotho</span>
          </footer>
        </article>
      </div>
    </main>
  );
}
