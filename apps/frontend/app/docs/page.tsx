import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  DatabaseBackup,
  Globe2,
  KeyRound,
  Mail,
  Network,
  Server,
  Settings2,
  ShieldCheck,
  Smartphone,
} from "lucide-react";

const sections = [
  ["packages", "Packages & limits"],
  ["onboarding", "Getting started"],
  ["dns", "DNS records"],
  ["nameservers", "Nameservers & glue"],
  ["dnssec", "DNSSEC"],
  ["mail", "Mail authentication"],
  ["clients", "Email clients"],
  ["api", "API access"],
  ["backups", "Backups & monitoring"],
  ["security", "Security"],
  ["owner", "Platform-owner configuration"],
  ["troubleshooting", "Troubleshooting"],
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return <section id={id} className="scroll-mt-24 rounded-3xl border border-[#dfe6e2] bg-white p-6 shadow-sm sm:p-8"><h2 className="text-2xl font-black tracking-[-.03em] text-[#17372f]">{title}</h2><div className="mt-4 space-y-4 text-sm leading-7 text-[#5f7068]">{children}</div></section>;
}

function InfoCard({ icon: Icon, title, children }: { icon: typeof Mail; title: string; children: React.ReactNode }) {
  return <div className="rounded-2xl border border-[#e3e9e6] bg-[#f8faf9] p-4"><div className="flex items-center gap-2.5"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#e9f1ee] text-[#285b55]"><Icon size={17}/></span><h3 className="text-sm font-black text-[#21342a]">{title}</h3></div><div className="mt-3 text-xs leading-6 text-[#65766e]">{children}</div></div>;
}

export default function DocumentationPage() {
  return <main className="min-h-screen bg-[#f4f6f4] text-[#21342a]">
    <header className="sticky top-0 z-30 border-b border-white/10 bg-[#123a38]/95 text-white backdrop-blur-xl"><div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-5 py-4 sm:px-8"><Link href="/" className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] font-black text-[#123a38]">MD</span><div><p className="text-sm font-black">Mailbox DNS</p><p className="text-[9px] font-bold uppercase tracking-[.14em] text-white/50">Documentation</p></div></Link><nav className="flex items-center gap-3 text-xs font-bold"><Link href="/pricing" className="hidden text-white/70 hover:text-white sm:inline">Pricing</Link><Link href="/service-status" className="hidden text-white/70 hover:text-white sm:inline">Status</Link><Link href="/login" className="rounded-lg border border-white/20 px-4 py-2">Sign in</Link></nav></div></header>

    <section className="border-b border-[#dfe6e2] bg-[linear-gradient(135deg,#123a38_0%,#1d504a_100%)] text-white"><div className="mx-auto max-w-[1240px] px-5 py-16 sm:px-8 lg:py-20"><div className="max-w-3xl"><div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.07] px-3 py-2 text-[10px] font-black uppercase tracking-[.13em] text-white/70"><BookOpen size={14}/>Public configuration manual</div><h1 className="mt-5 text-4xl font-black tracking-[-.045em] sm:text-5xl">Understand Mailbox DNS before changing your infrastructure.</h1><p className="mt-5 max-w-2xl text-sm leading-7 text-white/65">This guide explains packages, domain onboarding, authoritative DNS, mail configuration, DNSSEC, client settings, API access, backups and security in practical language. Exact hostnames and values for your organization are shown in your signed-in control panel.</p><div className="mt-7 flex flex-wrap gap-3"><Link href="/pricing" className="inline-flex items-center gap-2 rounded-xl bg-[#f1de8b] px-5 py-3 text-sm font-black text-[#123a38]">Compare packages <ArrowRight size={15}/></Link><Link href="/signup" className="rounded-xl border border-white/15 bg-white/[.07] px-5 py-3 text-sm font-black">Start free trial</Link></div></div></div></section>

    <div className="mx-auto grid max-w-[1240px] gap-7 px-5 py-10 sm:px-8 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-24 lg:self-start"><div className="rounded-2xl border border-[#dfe6e2] bg-white p-4 shadow-sm"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#7a8982]">In this manual</p><nav className="mt-3 space-y-1">{sections.map(([id,label])=><a key={id} href={`#${id}`} className="block rounded-lg px-3 py-2 text-xs font-bold text-[#53665d] hover:bg-[#eef4f1] hover:text-[#17372f]">{label}</a>)}</nav></div></aside>

      <div className="space-y-6">
        <Section id="packages" title="Packages & limits">
          <p>A package combines a monthly price with real resource limits. These numbers are not advertising estimates: the control plane uses them when deciding whether an organization may create another mailbox, onboard another domain, allocate more mailbox storage or create another API key.</p>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoCard icon={Mail} title="Mailboxes"><p><b>One mailbox is one individual email account.</b> Examples are <code>info@company.co.ls</code>, <code>accounts@company.co.ls</code> or an employee address. A 50-mailbox package allows up to 50 such accounts across the organization.</p></InfoCard>
            <InfoCard icon={Globe2} title="Hosted domains"><p>A hosted domain is a separate domain managed under the same subscription. A limit of 10 means the organization can onboard up to 10 different domains for DNS and/or mail services.</p></InfoCard>
            <InfoCard icon={Server} title="Allocated storage"><p>Storage is the organization&apos;s <b>shared allocated mailbox quota pool</b>. For example, 250 GB is shared across the organization; it is not automatically 250 GB for every mailbox.</p></InfoCard>
            <InfoCard icon={KeyRound} title="API keys"><p>API keys are credentials used by applications, scripts and integrations to automate approved platform operations. A 10-key limit means up to 10 active integration credentials.</p></InfoCard>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoCard icon={Network} title="Authoritative DNS + DNSSEC"><p>Mailbox DNS can become the official DNS authority for customer domains using PowerDNS. DNSSEC adds cryptographic signatures so resolvers can detect forged DNS answers.</p></InfoCard>
            <InfoCard icon={Smartphone} title="Webmail + IMAP/SMTP"><p>Users can read and send mail in the browser and can also connect Outlook, Thunderbird, Apple Mail, Android/iOS clients and other standards-based applications.</p></InfoCard>
            <InfoCard icon={ShieldCheck} title="SPF, DKIM & DMARC tooling"><p>SPF declares permitted senders, DKIM cryptographically signs outgoing messages, and DMARC tells receiving servers how to treat messages that fail authentication. Together they improve trust, anti-spoofing and deliverability.</p></InfoCard>
            <InfoCard icon={DatabaseBackup} title="Encrypted backups + monitoring"><p>Platform data is covered by encrypted backup workflows and operational monitoring. Monitoring watches service health and alerts operators; backup retention and recovery targets are operational policies, not extra mailbox storage.</p></InfoCard>
          </div>
          <p className="rounded-xl bg-[#fff8df] p-4 text-xs"><b>Important:</b> A package storage limit describes allocated mailbox quota. Actual disk capacity, backup storage and retention are separate platform-operational concerns.</p>
        </Section>

        <Section id="onboarding" title="Getting started">
          <p>The normal customer flow is: choose a package → create the organization account → add a domain → prove domain ownership → configure or delegate DNS → create mailboxes → configure mail clients and security.</p>
          <div className="grid gap-2 sm:grid-cols-2">{["Choose a package that covers expected users, domains and storage.","Add the domain in the control panel and publish the ownership-verification record shown there.","For Mailbox DNS authoritative hosting, register/delegate the nameservers shown by the platform at your registrar.","Wait for verification, then create mailboxes and publish the mail-authentication records shown in the panel."].map((item,index)=><div key={item} className="flex gap-3 rounded-xl border border-[#e4e9e6] p-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#123a38] text-[10px] font-black text-white">{index+1}</span><p className="text-xs leading-5">{item}</p></div>)}</div>
        </Section>

        <Section id="dns" title="DNS records">
          <p><b>A/AAAA</b> records point hostnames to IPv4/IPv6 addresses. <b>CNAME</b> aliases one hostname to another. <b>MX</b> specifies mail servers. <b>TXT</b> carries verification and authentication data such as SPF and DKIM. <b>CAA</b> restricts certificate authorities. <b>SRV</b> publishes service host/port information. <b>NS</b> identifies authoritative nameservers.</p>
          <p>TTL (Time To Live) controls how long resolvers cache a record. Lower TTLs can make planned migrations converge faster, but they also create more DNS query traffic. Do not change records simply to “make propagation faster” unless you understand the existing cache window.</p>
        </Section>

        <Section id="nameservers" title="Nameservers & glue records">
          <p>Delegation is configured at the domain registrar. It tells the parent registry which authoritative nameservers answer for the domain. When a nameserver is inside the same domain it serves—for example <code>ns1.example.co.ls</code> serving <code>example.co.ls</code>—the registrar/registry also needs a <b>glue (private/child nameserver) record</b> containing the nameserver&apos;s IP address to avoid a circular lookup.</p>
          <p>Always create and test the authoritative zone before changing delegation. The control panel shows the exact nameserver hostnames assigned to your domain.</p>
        </Section>

        <Section id="dnssec" title="DNSSEC">
          <p>DNSSEC signs authoritative zone data. A complete deployment needs keys/signatures on the authoritative DNS service and the correct DS information published at the parent/registrar. Enabling only one side can make the domain fail validation, so follow the control-panel DNSSEC state and registrar instructions as one coordinated operation.</p>
        </Section>

        <Section id="mail" title="Mail routing, SPF, DKIM & DMARC">
          <p>The domain&apos;s MX record directs incoming mail to the platform mail hostname. SPF defines which systems may send on behalf of the domain. DKIM publishes a public key in DNS while outgoing messages are signed using the corresponding private key. DMARC evaluates SPF/DKIM alignment and publishes the domain owner&apos;s policy.</p>
          <p>Use the exact MX, SPF, DKIM selector/value and DMARC recommendations generated for your domain. Do not copy another customer&apos;s DKIM record or private key.</p>
        </Section>

        <Section id="clients" title="Webmail & email-client configuration">
          <p>Webmail requires only a browser and the mailbox credentials. For standards-based clients, use the mail hostname shown in the control panel, the <b>full email address as username</b>, IMAPS on port <b>993</b> with TLS, and authenticated SMTP submission on port <b>587</b> with STARTTLS/TLS as instructed by the platform.</p>
          <p>Do not use public SMTP port 25 as a normal end-user submission port. Port 25 is primarily for server-to-server mail transport.</p>
        </Section>

        <Section id="api" title="API access">
          <p>API keys are intended for automation and integrations. Give each integration its own key, use the narrowest available scopes, store keys in a secret manager or protected environment variable, and revoke keys that are no longer needed. Never embed a secret API key in browser JavaScript or public source code.</p>
        </Section>

        <Section id="backups" title="Encrypted backups & monitoring">
          <p>Mailbox DNS includes operational backup and monitoring capabilities. Backups protect recoverable platform data and are encrypted using platform-controlled secrets. Monitoring covers application/mail/DNS service health and feeds operational dashboards and alerts. Backups are not a substitute for mailbox retention policies or a customer archive product unless a separate archive feature is explicitly enabled.</p>
        </Section>

        <Section id="security" title="Security practices">
          <p>Use MFA for privileged accounts, unique passwords, least-privilege tenant roles and scoped API keys. Keep devices and email clients updated, use TLS-enabled client settings, review active sessions and audit logs, and investigate unexpected DNS/mail changes immediately.</p>
          <p>DNS, mail and account security are connected: a compromised registrar, nameserver account or platform-owner account can affect an entire domain. Protect registrar and platform access with the same care as banking/admin credentials.</p>
        </Section>

        <Section id="owner" title="Platform-owner package configuration">
          <p>The platform owner can create and edit commercial packages under <b>Business → Packages & pricing</b>. Package price, mailbox limit, domain limit, storage allocation and API-key limit feed the public catalog and the same billing-entitlement system used during provisioning.</p>
          <p>Existing package codes are permanent identifiers used by signup/subscription flows. Change customer-facing names/pricing/limits carefully. The platform blocks deactivation of a package that is still assigned to a tenant; move those subscriptions first.</p>
        </Section>

        <Section id="troubleshooting" title="Troubleshooting checklist">
          <div className="space-y-2">{["DNS not resolving: confirm registrar delegation, glue records (when required), authoritative zone and firewall port 53 TCP/UDP.","Mail not arriving: verify MX resolves to the intended mail hostname and that server-to-server SMTP is reachable.","Mail going to spam: inspect SPF, DKIM and DMARC alignment plus sender/IP reputation; authentication alone cannot guarantee inbox placement.","Email client cannot connect: verify full email username, password, TLS, IMAPS 993 and submission 587 settings.","A package limit is reached: review organization usage and upgrade/edit the subscription instead of bypassing entitlement checks.","A change is unclear: use the support centre before changing nameservers, MX, DNSSEC or authentication records."].map(item=><div key={item} className="flex gap-2 rounded-xl bg-[#f7f9f8] p-3 text-xs leading-5"><CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600"/><span>{item}</span></div>)}</div>
        </Section>

        <div className="rounded-3xl bg-[#123a38] p-7 text-white"><div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/10 text-[#f1de8b]"><Settings2 size={20}/></span><div><h2 className="text-xl font-black">Use the panel for exact values.</h2><p className="mt-2 max-w-2xl text-xs leading-6 text-white/65">This manual explains how the system works. Your signed-in domain, DNS and mail screens remain the source of truth for generated verification tokens, nameserver targets, DKIM selectors, hostnames and other account-specific configuration.</p><Link href="/login" className="mt-4 inline-flex items-center gap-2 text-xs font-black text-[#f1de8b]">Sign in to configure resources <ArrowRight size={14}/></Link></div></div></div>
      </div>
    </div>

    <footer className="border-t border-[#dfe6e2] bg-white"><div className="mx-auto flex max-w-[1240px] flex-col gap-3 px-5 py-7 text-[10px] font-semibold text-[#819087] sm:flex-row sm:items-center sm:justify-between sm:px-8"><span>Mailbox DNS · Email · DNS · Hosting</span><span className="flex flex-wrap gap-4"><Link href="/pricing">Pricing</Link><Link href="/legal">Policies</Link><Link href="/service-status">Service status</Link><Link href="/login">Sign in</Link></span></div></footer>
  </main>;
}
