"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Popover, Tooltip } from "./ui";

type Module = { href: string; label: string; code: string };

const groups: Array<{ name: string; modules: Module[] }> = [
  { name: "Overview", modules: [
    { href: "/", label: "Command Centre", code: "01" },
    { href: "/intelligence", label: "Management Intelligence", code: "12" },
    { href: "/index", label: "System Manual", code: "DOC" },
  ] },
  { name: "Projects & sites", modules: [
    { href: "/projects", label: "Project Mobilisation", code: "06" },
    { href: "/projects/control", label: "Project Control", code: "06C" },
    { href: "/projects/risks", label: "Project Risks", code: "06R" },
    { href: "/planning", label: "Programme Control", code: "19" },
    { href: "/resources", label: "Resource Capacity", code: "20" },
    { href: "/communications", label: "Communications", code: "21" },
    { href: "/compliance", label: "Compliance Control", code: "22" },
    { href: "/data-quality", label: "Data Quality", code: "23" },
    { href: "/authority", label: "Approval Authority", code: "24" },
    { href: "/changes", label: "Change Control", code: "25" },
    { href: "/site-operations", label: "Site Operations", code: "07" },
    { href: "/site-operations/control", label: "Site Operations Control", code: "07C" },
    { href: "/closeout", label: "Project Closeout", code: "17" },
    { href: "/mobile", label: "Field Capture", code: "14" },
  ] },
  { name: "Commercial", modules: [
    { href: "/tenders", label: "Tender Management", code: "05" },
    { href: "/tenders/control", label: "Tender Control", code: "05C" },
    { href: "/procurement", label: "Procurement & Stores", code: "09" },
    { href: "/procurement/control", label: "Procurement Control", code: "09C" },
    { href: "/subcontracts", label: "Subcontract Management", code: "10" },
    { href: "/subcontracts/control", label: "Subcontract Control", code: "10C" },
    { href: "/commercial", label: "Cost & Commercial", code: "11" },
    { href: "/contract-control", label: "Contract Control", code: "34" },
    { href: "/finance", label: "Finance & Cash Control", code: "18" },
    { href: "/assistants", label: "Algorithmic Assistants", code: "AI" },
  ] },
  { name: "People & control", modules: [
    { href: "/workforce", label: "Workforce", code: "03" },
    { href: "/workforce/setup", label: "Workforce Setup", code: "03C" },
    { href: "/development", label: "HR Development", code: "15" },
    { href: "/fleet", label: "Fleet & Plant", code: "04" },
    { href: "/fleet/control", label: "Fleet Control", code: "04C" },
    { href: "/assurance", label: "HSE & Quality", code: "13" },
    { href: "/support", label: "Support Centre", code: "27" },
    { href: "/environment", label: "Environment & Sustainability", code: "28" },
    { href: "/tools", label: "Tools & Calibration", code: "29" },
    { href: "/client-portal", label: "Client Portal", code: "30" },
    { href: "/vendor-portal", label: "Vendor Portal", code: "31" },
    { href: "/business-development", label: "Business Development", code: "32" },
    { href: "/client-accounts", label: "Client Accounts", code: "33" },
    { href: "/access", label: "Access & Security", code: "02" },
    { href: "/rollout", label: "Professional Rollout", code: "16" },
    { href: "/automation", label: "Operational Automation", code: "35" },
  ] },
];

function activePath(pathname: string, href: string) {
  return pathname === href;
}

export function BuildTrackNavigation() {
  const pathname = usePathname();
  return (
    <aside className="bt-sidebar" aria-label="Nthane Brothers application navigation">
      <Link className="bt-brand" href="/" aria-label="Nthane Brothers command centre">
        <span className="bt-brand-mark">NB</span>
        <span className="bt-brand-copy"><strong>Nthane Brothers</strong><small>Construction Management System</small></span>
      </Link>
      <div className="bt-scope"><small>Operational scope</small><strong>One company platform</strong><span>Head office · branches · sites</span></div>
      <nav className="bt-nav-links">
        {groups.map((group) => <section className="bt-nav-group" key={group.name} aria-label={group.name}>
          <p>{group.name}</p>
          {group.modules.map((module) => {
            const active = activePath(pathname, module.href);
            return <Link className="bt-nav-link" href={module.href} key={module.href} aria-current={active ? "page" : undefined}>
              <span className="bt-nav-code">{module.code}</span><span>{module.label}</span>
            </Link>;
          })}
        </section>)}
      </nav>
      <div className="bt-nav-footer"><small>Developed by</small><strong>Ithute Solution</strong><span>Controlled · auditable · branch-aware</span><Link href="/index">Open full user manual</Link><span>Double-tap Shift: routes · Ctrl + Shift: forms</span><Popover label={<Tooltip content="Open workspace guidance">Workspace guide</Tooltip>}><strong>Nthane Brothers workspace</strong><p>Use the Display control to adjust zoom, reading size and workstation density. Focus workspace hides the navigation until you choose “Show navigation”.</p><p>Every operational action remains subject to your role, branch/site scope and maker/checker controls.</p></Popover></div>
    </aside>
  );
}
