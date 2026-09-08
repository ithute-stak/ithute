"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { getManualDetail } from "../lib/manual-details";
import { MANUAL_ENTRIES, MANUAL_GROUPS, ROLE_GUIDE, type ManualEntry } from "../lib/system-manual";
import { PublicHeader } from "../components/public-header";
import styles from "./manual.module.css";
import detailStyles from "./manual-expanded.module.css";

const ui = { ...styles, ...detailStyles };

const QUICK_FIND = [
  ["Capture fuel", "/fleet", "Fleet & Plant → Fuel transaction"],
  ["Add an employee", "/workforce", "Workforce → Employee"],
  ["Prepare payroll", "/workforce", "Workforce → Timesheets / Payroll batch"],
  ["Request materials", "/procurement", "Procurement & Stores → Requisition"],
  ["Create a purchase order", "/procurement", "Procurement & Stores → Purchase order"],
  ["Receive stock", "/procurement", "Procurement & Stores → Goods receipt / stores"],
  ["Prepare a tender", "/tenders", "Tender Management → Tender checklist / BOQ / submission"],
  ["Approve a tender", "/tenders/control", "Tender Control → independent gate review"],
  ["Create a project", "/projects", "Project Mobilisation → project / readiness"],
  ["Record project risk", "/projects/risks", "Project Risks → risk register"],
  ["Update programme", "/planning", "Programme Control → activity / progress update"],
  ["Record a delay", "/planning", "Programme Control → delay record"],
  ["Prepare a contract notice", "/contract-control", "Contract Control → New notice"],
  ["Complete a daily site report", "/site-operations", "Site Operations → Daily site report"],
  ["Record site material use", "/site-operations", "Site Operations → Material usage; stock ledger remains in Procurement & Stores"],
  ["Record a safety/quality finding", "/assurance", "HSE & Quality → inspection / finding"],
  ["Register a subcontractor", "/subcontracts", "Subcontract Management → Subcontractor"],
  ["Prepare a subcontract certificate", "/subcontracts", "Subcontract Management → Certificate"],
  ["Prepare a client valuation", "/commercial", "Cost & Commercial → Valuation"],
  ["Record an invoice", "/finance", "Finance & Cash Control → Invoice"],
  ["Prepare a payment request", "/finance", "Finance & Cash Control → Payment request"],
  ["Reset a user's password", "/access", "Access & Security → Password reset"],
  ["Find management reports", "/intelligence", "Management Intelligence → choose the required management view"],
  ["Create an alert rule", "/automation", "Operational Automation → New rule"],
] as const;

const WORKFLOW = [
  ["01", "Opportunity", "Business Development records the lead, client, likely value, owner and next action."],
  ["02", "Tender", "Tender Management controls the bid decision, compliance, estimate, approval and real submission evidence."],
  ["03", "Mobilise", "Project Mobilisation establishes project identity, budget, programme, people, plant, risks and readiness."],
  ["04", "Execute", "Site, workforce, fleet, procurement and subcontract modules capture what actually happens during delivery."],
  ["05", "Control", "Commercial, finance, programme, assurance, compliance, data quality and intelligence provide governance."],
];

const OPERATING_RULES = [
  ["Scope first", "Always confirm company, branch, site and project before creating a record. Correct information in the wrong scope is still wrong data."],
  ["Draft before approval", "Prepare the record and evidence first. Submit only when it is ready for the next controlled step."],
  ["Maker / checker", "Where independent approval is enabled, the preparer cannot approve or verify their own work."],
  ["Evidence matters", "A tick, status or narrative is not a substitute for the real document, receipt, measurement, certificate, instruction or other evidence where evidence is required."],
  ["Source of truth", "Summary/control screens show information, but corrections must be made in the module that owns the underlying business record."],
  ["External action is external", "The system may record payment, submission, dispatch or communication evidence; it must not claim the real-world action happened until real evidence is supplied."],
] as const;

function anchor(entry: ManualEntry) {
  return `screen-${entry.route.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "home"}`;
}

function detailSearch(entry: ManualEntry) {
  const detail = getManualDetail(entry);
  return [
    detail.useWhen,
    ...detail.before,
    ...detail.screenAreas,
    ...detail.keyData,
    ...detail.controls,
    detail.sourceOfTruth,
    ...detail.commonMistakes,
    detail.result,
    ...detail.next,
    detail.example ?? "",
  ];
}

export function ManualClient({ authenticated }: { authenticated: boolean }) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const q = query.trim().toLowerCase();

  const filtered = useMemo(() => MANUAL_ENTRIES.filter((entry) => {
    if (!q) return true;
    return [
      entry.title, entry.route, entry.group, entry.summary, entry.roles,
      ...entry.find, ...entry.steps,
      ...(entry.forms ?? []).flatMap((form) => [form.label, form.purpose]),
      ...detailSearch(entry),
    ].join(" ").toLowerCase().includes(q);
  }), [q]);

  function hrefFor(entry: ManualEntry | { route: string; public?: boolean; dynamicRoute?: boolean }) {
    if (entry.dynamicRoute) return "#vendor-token";
    if (authenticated || entry.public) return entry.route;
    return `/login?returnTo=${encodeURIComponent(entry.route)}`;
  }

  function toggle(route: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(route)) next.delete(route);
      else next.add(route);
      return next;
    });
  }

  function expandRoutes(routes: string[]) {
    setExpanded((current) => new Set([...current, ...routes]));
  }

  function collapseRoutes(routes: string[]) {
    setExpanded((current) => {
      const next = new Set(current);
      routes.forEach((route) => next.delete(route));
      return next;
    });
  }

  return <main className={`${ui.page} ${authenticated ? "" : ui.publicTop}`}>
    {!authenticated ? <PublicHeader /> : null}

    <section className={ui.hero}>
      <div className={ui.heroGrid}>
        <div>
          <p className={ui.eyebrow}>Official operating & training manual · Nthane Brothers</p>
          <h1>Know exactly where to find it — and exactly how to use it.</h1>
          <p className={ui.heroLead}>This manual is designed for a new employee who has never used the system. Search by the task you want to perform, identify the screen that owns the record, read the short guide, then expand the screen for full instructions covering prerequisites, screen areas, information to prepare, controls, common mistakes, expected result and the next step.</p>
        </div>
        <aside className={ui.heroCard}>
          <strong>Developed and supported by Ithute Solution</strong>
          <p>For implementation, training, system support or product enquiries, contact the developer directly.</p>
          <div className={ui.contactRow}>
            <a className={ui.contact} href="mailto:thekoetlisi@gmail.com">thekoetlisi@gmail.com</a>
            <a className={ui.contact} href="tel:+26659001394">+266 5900 1394</a>
            <a className={ui.contact} href="https://wa.me/26659001394" target="_blank" rel="noreferrer">WhatsApp</a>
          </div>
        </aside>
      </div>
    </section>

    <div className={ui.quickBar}>
      <div className={ui.quickInner}>
        <input className={ui.search} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search anything: fuel, payroll, bid security, stock transfer, EOT notice, invoice, user role..." aria-label="Search the full user manual" />
        <div className={ui.quickActions}>
          <button className={ui.detailAction} onClick={() => expandRoutes(filtered.map((entry) => entry.route))}>Expand all details</button>
          <button className={ui.detailAction} onClick={() => collapseRoutes(filtered.map((entry) => entry.route))}>Collapse all</button>
        </div>
      </div>
    </div>

    <div className={ui.layout}>
      <aside className={ui.side} aria-label="Manual contents">
        <p className={ui.sideTitle}>Manual contents</p>
        <a href="#start">Start here</a>
        <a href="#rules">How controlled records work</a>
        <a href="#find">Where do I find…?</a>
        <a href="#workflow">How the system flows</a>
        <a href="#roles">User roles</a>
        <div className={ui.sideDivider} />
        {MANUAL_GROUPS.map((group) => <a key={group} href={`#group-${group.replace(/[^a-z0-9]+/gi,"-").toLowerCase()}`}>{group}</a>)}
        <div className={ui.sideDivider} />
        <a href="#shortcuts">Global search shortcuts</a>
        <a href="#about">About &amp; support</a>
      </aside>

      <div className={ui.content}>
        <section id="start" className={ui.section}>
          <div className={ui.introGrid}>
            <div className={ui.metric}><span>Documented screens</span><strong>{MANUAL_ENTRIES.length}</strong><small>Every operational/authentication screen</small></div>
            <div className={ui.metric}><span>Verified seeded roles</span><strong>{ROLE_GUIDE.length}</strong><small>Role + scope determine access</small></div>
            <div className={ui.metric}><span>Manual depth</span><strong>2 levels</strong><small>Quick guide + expanded training</small></div>
          </div>
          <div className={ui.sectionHead}><div><h2>How to use this manual</h2><p>The first level helps you find the right screen quickly. The expanded level teaches you how to operate it correctly and how it connects to the rest of the system.</p></div><span className={ui.groupPill}>Navigation + training</span></div>
          <div className={ui.finderGrid}>
            <div className={ui.finder}><strong>1. Search by the work you want to do</strong><span>Use natural terms such as “fuel”, “new employee”, “approve tender”, “receive material”, “contract notice”, “payroll”, “invoice” or “project risk”.</span></div>
            <div className={ui.finder}><strong>2. Read the quick card first</strong><span>The card tells you what lives on the screen, the normal sequence, who normally uses it and which forms/actions are available.</span></div>
            <div className={ui.finder}><strong>3. Expand for full instructions</strong><span>Every screen has a full training section. Open it before doing an unfamiliar process, especially approvals, commercial transactions, finance, payroll, site evidence or security administration.</span></div>
            <div className={ui.finder}><strong>4. Open the real screen</strong><span>{authenticated ? "You are authenticated, so Open screen takes you directly to the operational workspace." : "You can read this manual publicly. Operational links take you to Sign In, then return you to the screen you selected."}</span></div>
          </div>
        </section>

        <section id="rules" className={ui.section}>
          <div className={ui.sectionHead}><div><h2>How controlled records work</h2><p>These principles apply throughout the system. Understanding them prevents most user mistakes.</p></div><span className={ui.groupPill}>Read this first</span></div>
          <div className={ui.ruleGrid}>
            {OPERATING_RULES.map(([title, copy], index) => <div className={ui.ruleCard} key={title}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{title}</strong><p>{copy}</p></div></div>)}
          </div>
          <div className={ui.statusFlow}>
            <strong>Typical controlled lifecycle</strong>
            <span>Draft</span><b>→</b><span>Submitted</span><b>→</b><span>Reviewed / Approved</span><b>→</b><span>Posted / Issued / Completed</span>
            <p>Not every module uses every status, but the principle is the same: prepare first, submit for control, then complete the real operational step only when the required gate has passed. Rejected/returned records should be corrected and resubmitted rather than hidden.</p>
          </div>
        </section>

        <section id="find" className={ui.section}>
          <div className={ui.sectionHead}><div><h2>Where do I find…?</h2><p>A practical task-to-screen index for common questions. Use the full search above for anything not shown here.</p></div><span className={ui.groupPill}>Quick finder</span></div>
          <div className={ui.finderGrid}>
            {QUICK_FIND.filter(([task,,where]) => !q || `${task} ${where}`.toLowerCase().includes(q)).map(([task, route, where]) => {
              const entry = MANUAL_ENTRIES.find((item) => item.route === route)!;
              return <div className={ui.finder} key={task}><strong>{task}</strong><span>{where}</span><div className={ui.finderLinks}><a href={`#${anchor(entry)}`}>Read instructions</a><Link href={hrefFor(entry)}>Open {entry.title} →</Link></div></div>;
            })}
          </div>
        </section>

        <section id="workflow" className={ui.section}>
          <div className={ui.sectionHead}><div><h2>How the system flows</h2><p>Most work moves through an end-to-end construction lifecycle. Use this to understand why the same project can appear in several modules without those modules owning the same information.</p></div><span className={ui.groupPill}>End to end</span></div>
          <div className={ui.workflow}>{WORKFLOW.map(([step,title,copy]) => <div className={ui.workflowStep} key={step}><span>{step}</span><strong>{title}</strong><p>{copy}</p></div>)}</div>
        </section>

        <section id="roles" className={ui.section}>
          <div className={ui.sectionHead}><div><h2>User roles</h2><p>Roles define responsibility; scope defines where that responsibility applies. A person can have more than one assignment. Seeing a screen does not automatically mean the user can create, approve or view sensitive information on it.</p></div><span className={ui.groupPill}>{ROLE_GUIDE.length} roles</span></div>
          <div className={ui.roleGrid}>{ROLE_GUIDE.map(([role,copy]) => <div className={ui.role} key={role}><strong>{role}</strong><p>{copy}</p></div>)}</div>
        </section>

        {MANUAL_GROUPS.map((group) => {
          const entries = filtered.filter((entry) => entry.group === group);
          if (!entries.length) return null;
          const id = `group-${group.replace(/[^a-z0-9]+/gi,"-").toLowerCase()}`;
          const routes = entries.map((entry) => entry.route);
          return <section id={id} className={ui.section} key={group}>
            <div className={ui.sectionHead}>
              <div><h2>{group}</h2><p>Each card gives the quick operating guide. Select <b>Expand for full instructions</b> for complete training guidance.</p></div>
              <div className={ui.sectionActions}><span className={ui.groupPill}>{entries.length} screen{entries.length === 1 ? "" : "s"}</span><button onClick={() => expandRoutes(routes)}>Expand section</button><button onClick={() => collapseRoutes(routes)}>Collapse</button></div>
            </div>
            <div className={ui.moduleGrid}>
              {entries.map((entry, index) => {
                const detail = getManualDetail(entry);
                const isExpanded = expanded.has(entry.route);
                return <article id={anchor(entry)} className={`${ui.module} ${isExpanded ? ui.moduleExpanded : ""}`} key={entry.route}>
                  <div className={ui.moduleTop}>
                    <span className={ui.moduleMark}>{String(index + 1).padStart(2,"0")}</span>
                    <div><h3>{entry.title}</h3><p>{entry.summary} <strong>{entry.route}</strong></p></div>
                    <div className={ui.moduleActions}>
                      <button className={ui.expandButton} onClick={() => toggle(entry.route)} aria-expanded={isExpanded}>{isExpanded ? "Hide full instructions" : "Expand for full instructions"}</button>
                      {entry.dynamicRoute ? <span id="vendor-token" className={`${ui.open} ${ui.openSecondary}`}>Issued token link only</span> : <Link className={ui.open} href={hrefFor(entry)}>{authenticated || entry.public ? "Open screen" : "Sign in & open"} →</Link>}
                    </div>
                  </div>

                  <div className={ui.moduleBody}>
                    <div className={ui.block}><h4>Where / what to find here</h4><ul>{entry.find.map((item) => <li key={item}>{item}</li>)}</ul>{entry.directRoute ? <div className={ui.note}>This advanced workspace is available in the sidebar and global route search.</div> : null}</div>
                    <div className={ui.block}><h4>Normal operating sequence</h4><ol>{entry.steps.map((step) => <li key={step}>{step}</li>)}</ol></div>
                    <div className={ui.block}><h4>Who uses it</h4><p className={ui.roles}>{entry.roles}</p>{entry.forms?.length ? <><h4 className={ui.subheading}>Forms / actions</h4><div className={ui.forms}>{entry.forms.map((form) => <span className={ui.formPill} title={form.purpose} key={form.label}>{form.label}</span>)}</div></> : null}</div>
                  </div>

                  {isExpanded ? <div className={ui.detailPanel}>
                    <div className={ui.detailIntro}>
                      <span className={ui.detailBadge}>Full operating instructions</span>
                      <div><h4>When should I use {entry.title}?</h4><p>{detail.useWhen}</p></div>
                    </div>

                    <div className={ui.detailGrid}>
                      <section className={ui.detailCard}><h5>Before you start</h5><p className={ui.detailLead}>Have these items ready before opening or submitting a record.</p><ul>{detail.before.map((item) => <li key={item}>{item}</li>)}</ul></section>
                      <section className={ui.detailCard}><h5>What you will see on this screen</h5><p className={ui.detailLead}>These are the main areas/tabs/record groups to look for.</p><ul>{detail.screenAreas.map((item) => <li key={item}>{item}</li>)}</ul></section>
                      <section className={ui.detailCard}><h5>Information you should have ready</h5><p className={ui.detailLead}>The exact fields vary by form, but these are the important business facts/evidence.</p><ul>{detail.keyData.map((item) => <li key={item}>{item}</li>)}</ul></section>
                    </div>

                    <section className={ui.procedure}>
                      <div className={ui.procedureHead}><div><h5>Step-by-step procedure</h5><p>Follow the steps in order. Do not skip evidence or approval steps just because a button is available.</p></div><span>{entry.steps.length} core steps</span></div>
                      <ol className={ui.procedureList}>{entry.steps.map((step, stepIndex) => <li key={step}><span className={ui.stepNumber}>{stepIndex + 1}</span><div><strong>{step}</strong><p>{stepIndex === 0 ? "Confirm the correct scope and source record before entering data." : stepIndex === entry.steps.length - 1 ? "Before leaving the screen, confirm the record status, evidence and next responsible person." : "Complete the required information accurately, save the record, and resolve validation warnings before continuing."}</p></div></li>)}</ol>
                    </section>

                    {entry.forms?.length ? <section className={ui.formGuide}>
                      <h5>Forms and actions on this screen</h5>
                      <div className={ui.formGuideGrid}>{entry.forms.map((form) => <div key={form.label}><strong>{form.label}</strong><p>{form.purpose}</p><span>Complete required fields → attach/reference evidence where needed → save as draft → submit/approve only when ready.</span></div>)}</div>
                    </section> : null}

                    <div className={ui.detailGrid}>
                      <section className={`${ui.detailCard} ${ui.controlCard}`}><h5>Controls & approvals</h5><ul>{detail.controls.map((item) => <li key={item}>{item}</li>)}</ul></section>
                      <section className={`${ui.detailCard} ${ui.sourceCard}`}><h5>Source of truth</h5><p>{detail.sourceOfTruth}</p><div className={ui.sourceLabel}>If a number is wrong, correct it in the owning module — not in a summary/report screen.</div></section>
                      <section className={`${ui.detailCard} ${ui.warningCard}`}><h5>Common mistakes to avoid</h5><ul>{detail.commonMistakes.map((item) => <li key={item}>{item}</li>)}</ul></section>
                    </div>

                    {detail.example ? <div className={ui.example}><strong>Practical example</strong><p>{detail.example}</p></div> : null}

                    <div className={ui.outcomeGrid}>
                      <div><span>Expected result</span><strong>{detail.result}</strong></div>
                      <div><span>What to do next</span><ul>{detail.next.map((item) => <li key={item}>{item}</li>)}</ul></div>
                    </div>

                    <div className={ui.detailFooter}>
                      <button onClick={() => toggle(entry.route)}>Collapse instructions</button>
                      {entry.dynamicRoute ? null : <Link className={ui.open} href={hrefFor(entry)}>{authenticated || entry.public ? `Open ${entry.title}` : `Sign in & open ${entry.title}`} →</Link>}
                    </div>
                  </div> : null}
                </article>;
              })}
            </div>
          </section>;
        })}

        <section id="shortcuts" className={ui.section}>
          <div className={ui.sectionHead}><div><h2>Global search shortcuts</h2><p>Authenticated users can move around the system without hunting through the sidebar.</p></div><span className={ui.groupPill}>Keyboard</span></div>
          <div className={ui.finderGrid}>
            <div className={ui.finder}><strong>Global route search</strong><span>Double-tap <b>Shift</b> within about half a second. You can also hold <b>Shift</b> and double-click a non-form area. Search by screen name, route or business term and press Enter to open it.</span>{authenticated ? <button onClick={() => window.dispatchEvent(new Event("nth:open-route-search"))} className={ui.open}>Open route search</button> : null}</div>
            <div className={ui.finder}><strong>Global form/action finder</strong><span>Press and release <b>Ctrl + Shift</b> as a chord. Search for an action such as “purchase order”, “fuel transaction”, “employee” or “contract notice”, then use the module selector if needed.</span>{authenticated ? <button onClick={() => window.dispatchEvent(new Event("nth:open-form-search"))} className={ui.open}>Open form finder</button> : null}</div>
          </div>
        </section>

        <section id="about" className={ui.section}>
          <div className={ui.about}>
            <h2>About the system</h2>
            <p>The Nthane Brothers Construction Management System is a single-company construction operations platform for Head Office, branches and construction sites. It connects business development, tendering, mobilisation, daily site operations, workforce, payroll preparation, fleet and plant, procurement and stores, subcontractors, commercial control, finance, programme/resource control, HSE/quality, compliance, communications, external evidence sharing, closeout and management intelligence.</p>
            <div className={ui.aboutGrid}>
              <div className={ui.aboutCard}><strong>Control philosophy</strong><p>Role + scope access, maker/checker approval, auditable evidence and controlled operational records. The system records and controls real actions; it does not falsely claim external payments, messages or submissions occurred.</p></div>
              <div className={ui.aboutCard}><strong>Developer &amp; support</strong><p>Ithute Solution · thekoetlisi@gmail.com · +266 5900 1394 · WhatsApp +266 5900 1394.</p><div className={ui.contactRow}><a className={ui.contact} href="mailto:thekoetlisi@gmail.com">Email developer</a><a className={ui.contact} href="https://wa.me/26659001394" target="_blank" rel="noreferrer">Open WhatsApp</a></div></div>
            </div>
          </div>
          <footer className={ui.footer}><span>Nthane Brothers Construction Management System</span><span>Developed by Ithute Solution · Lesotho</span></footer>
        </section>
      </div>
    </div>
  </main>;
}
