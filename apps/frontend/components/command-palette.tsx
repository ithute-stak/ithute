"use client";

import {
  Activity,
  Bell,
  BookOpen,
  Building2,
  CircleDollarSign,
  Globe2,
  KeyRound,
  LayoutDashboard,
  Mail,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

type Command = { label: string; hint: string; href: string; icon: LucideIcon; keywords?: string };

const commands: Command[] = [
  { label: "Command centre", hint: "Dashboard and platform overview", href: "/dashboard", icon: LayoutDashboard, keywords: "home overview" },
  { label: "Getting started", hint: "Onboarding checklist", href: "/onboarding", icon: Sparkles, keywords: "setup start" },
  { label: "Organizations", hint: "Companies, memberships and roles", href: "/organizations", icon: Building2, keywords: "tenant company team" },
  { label: "Domain portfolio", hint: "Domains and verification", href: "/domains", icon: Globe2, keywords: "domain verify nameserver" },
  { label: "DNS zones", hint: "Authoritative records", href: "/dns", icon: Server, keywords: "records powerdns a mx txt" },
  { label: "DNS security", hint: "DNSSEC and protection", href: "/dns-security", icon: ShieldCheck, keywords: "dnssec security ds" },
  { label: "Edge control centre", hint: "Edge applications, origins and policy state", href: "/edge", icon: ShieldCheck, keywords: "edge waf cdn origin security" },
  { label: "Mailboxes", hint: "Hosted mail accounts", href: "/mailboxes", icon: Mail, keywords: "mail users inbox" },
  { label: "Webmail", hint: "Open !thute Mail", href: "/webmail", icon: Send, keywords: "email compose inbox gmail" },
  { label: "Transactional email", hint: "SMTP credentials and sending", href: "/transactional-email", icon: Send, keywords: "smtp api sender" },
  { label: "Delivery & queues", hint: "Mail delivery operations", href: "/delivery", icon: Server, keywords: "queue deferred bounce" },
  { label: "Billing", hint: "Subscription and invoices", href: "/billing", icon: CircleDollarSign, keywords: "payment invoice plan" },
  { label: "Notifications", hint: "Platform alerts", href: "/notifications", icon: Bell, keywords: "alerts bell" },
  { label: "Security", hint: "Account and platform security", href: "/security", icon: ShieldCheck, keywords: "mfa password sessions" },
  { label: "API access", hint: "Automation credentials", href: "/api-access", icon: KeyRound, keywords: "token key" },
  { label: "Audit & activity", hint: "Infrastructure change history", href: "/audit", icon: Activity, keywords: "logs history actions" },
  { label: "Settings", hint: "Platform preferences", href: "/settings", icon: Settings, keywords: "preferences account" },
  { label: "Help centre", hint: "Guides and DNS help", href: "/help", icon: BookOpen, keywords: "docs support guide" },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((item) => `${item.label} ${item.hint} ${item.keywords || ""}`.toLowerCase().includes(needle));
  }, [query]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    const id = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    setActive((current) => Math.min(current, Math.max(filtered.length - 1, 0)));
  }, [filtered.length]);

  function go(command?: Command) {
    if (!command) return;
    setOpen(false);
    router.push(command.href);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[115] flex items-start justify-center bg-black/35 p-3 pt-[10vh] backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="Mailbox DNS command palette" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-[#dfe6e2] bg-white shadow-[0_28px_80px_rgba(17,45,35,.24)]">
        <div className="flex items-center gap-3 border-b border-[#e6ebe8] px-4">
          <Search size={18} className="text-[#718078]"/>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(value + 1, filtered.length - 1)); }
              if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(value - 1, 0)); }
              if (event.key === "Enter") { event.preventDefault(); go(filtered[active]); }
            }}
            placeholder="Search Mailbox DNS or jump to a module"
            className="h-14 min-w-0 flex-1 border-0 bg-transparent text-[13px] outline-none"
            aria-label="Search Mailbox DNS"
          />
          <button onClick={() => setOpen(false)} className="grid h-8 w-8 place-items-center rounded-lg text-[#718078] hover:bg-[#f1f5f2]" aria-label="Close command palette"><X size={15}/></button>
        </div>
        <div className="max-h-[56vh] overflow-y-auto p-2">
          {filtered.length ? filtered.map((item, index) => {
            const Icon = item.icon;
            return (
              <button
                key={item.href}
                onMouseEnter={() => setActive(index)}
                onClick={() => go(item)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left ${index === active ? "bg-[#eef4f1]" : "hover:bg-[#f7f9f8]"}`}
              >
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[#24554f] shadow-sm ring-1 ring-[#e4eae6]"><Icon size={16}/></div>
                <div className="min-w-0 flex-1"><p className="truncate text-[12px] font-black text-[#21342a]">{item.label}</p><p className="mt-0.5 truncate text-[10px] text-[#7b8982]">{item.hint}</p></div>
                <span className="hidden text-[9px] font-bold text-[#98a39d] sm:block">Enter</span>
              </button>
            );
          }) : <div className="grid min-h-36 place-items-center p-6 text-center"><div><p className="text-sm font-black text-[#21342a]">No matching destination</p><p className="mt-1 text-[11px] text-[#7b8982]">Try a domain, mailbox, edge, billing, DNS or settings keyword.</p></div></div>}
        </div>
        <div className="flex items-center justify-between border-t border-[#e6ebe8] bg-[#fafcfb] px-4 py-2 text-[9px] font-bold text-[#8a9690]">
          <span>↑ ↓ navigate · Enter open · Esc close</span>
          <span className="ithute-kbd">Ctrl K</span>
        </div>
      </div>
    </div>
  );
}
