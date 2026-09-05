"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  ChevronDown,
  CircleDollarSign,
  Globe2,
  Headphones,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  Plus,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  UsersRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { apiJson, PLATFORM_API_URL } from "@/lib/platform-api";
import { useStablePopover } from "@/components/stable-popover";

const SIDEBAR_KEY = "ithute:sidebar:collapsed";

type NavChild = { label: string; href: string; icon: LucideIcon };
type NavGroup = { label: string; href?: string; icon: LucideIcon; children?: NavChild[] };
type Me = { email?: string };

const navigation: NavGroup[] = [
  { label: "Command centre", href: "/dashboard", icon: LayoutDashboard },
  { label: "Getting started", href: "/onboarding", icon: Sparkles },
  {
    label: "Organizations",
    icon: Building2,
    children: [{ label: "Companies & memberships", href: "/organizations", icon: Building2 }],
  },
  {
    label: "Domains & DNS",
    icon: Globe2,
    children: [
      { label: "Domain portfolio", href: "/domains", icon: Globe2 },
      { label: "DNS zones", href: "/dns", icon: Server },
      { label: "DNS security", href: "/dns-security", icon: ShieldCheck },
    ],
  },
  {
    label: "Edge & security",
    icon: ShieldCheck,
    children: [{ label: "Edge control centre", href: "/edge", icon: ShieldCheck }],
  },
  {
    label: "Mail platform",
    icon: Mail,
    children: [
      { label: "Mailboxes", href: "/mailboxes", icon: Mail },
      { label: "Professional email", href: "/professional-email", icon: BriefcaseBusiness },
      { label: "Webmail", href: "/webmail", icon: Send },
      { label: "Transactional email", href: "/transactional-email", icon: Send },
      { label: "Delivery & queues", href: "/delivery", icon: Server },
    ],
  },
  {
    label: "Hosting company",
    icon: Building2,
    children: [{ label: "Reseller & white-label", href: "/hosting-company", icon: Building2 }],
  },
  {
    label: "Business",
    icon: CircleDollarSign,
    children: [
      { label: "Billing & subscription", href: "/billing", icon: CircleDollarSign },
      { label: "Notifications", href: "/notifications", icon: Bell },
      { label: "Support centre", href: "/support", icon: Headphones },
      { label: "Business operations", href: "/business-operations", icon: BriefcaseBusiness },
    ],
  },
  {
    label: "Governance & control",
    icon: ShieldCheck,
    children: [
      { label: "!thute Auth & Push", href: "/ithute-platform", icon: ShieldCheck },
      { label: "Security", href: "/security", icon: ShieldCheck },
      { label: "API access", href: "/api-access", icon: KeyRound },
      { label: "Audit & activity", href: "/audit", icon: Activity },
      { label: "Team access", href: "/organizations", icon: UsersRound },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
  {
    label: "Operations",
    icon: Activity,
    children: [
      { label: "Status centre", href: "/status", icon: Activity },
      { label: "Help & DNS guide", href: "/help", icon: BookOpen },
    ],
  },
];

function active(path: string, href: string) {
  return path === href || path.startsWith(`${href}/`);
}

function NavItem({ group, path, compact, onGo }: { group: NavGroup; path: string; compact: boolean; onGo: () => void }) {
  const isActive = Boolean(
    group.href ? active(path, group.href) : group.children?.some((child) => active(path, child.href)),
  );
  const [sectionOpen, setSectionOpen] = useState(isActive);
  const compactMenu = useStablePopover();
  const Icon = group.icon;

  if (group.href) {
    return (
      <Link
        href={group.href}
        onClick={onGo}
        title={compact ? group.label : undefined}
        aria-current={isActive ? "page" : undefined}
        className={`flex min-h-10 items-center rounded-xl text-[13px] font-semibold transition ${compact ? "justify-center px-2" : "gap-3 px-3"} ${
          isActive
            ? "bg-white/[.12] text-white shadow-[inset_3px_0_0_#d8c56a,0_6px_16px_rgba(0,0,0,.08)]"
            : "text-[#b8cbc4] hover:bg-white/[.07] hover:text-white"
        }`}
      >
        <Icon size={16} />
        {compact ? null : group.label}
      </Link>
    );
  }

  if (compact) {
    return (
      <div ref={compactMenu.rootRef} className="relative">
        <button
          ref={compactMenu.triggerRef}
          type="button"
          title={group.label}
          aria-haspopup="menu"
          aria-expanded={compactMenu.open}
          onClick={compactMenu.toggle}
          className={`flex min-h-10 w-full items-center justify-center rounded-xl px-2 transition ${isActive || compactMenu.open ? "bg-white/[.10] text-white" : "text-[#b8cbc4] hover:bg-white/[.07] hover:text-white"}`}
        >
          <Icon size={16} />
        </button>
        {compactMenu.open ? (
          <div role="menu" className="ithute-dropdown-panel absolute left-[54px] top-0 z-[70] w-64 border-white/[.08] bg-[#123a38] p-2 text-white">
            <div className="px-3 pb-2 pt-1 text-[9px] font-black uppercase tracking-[.14em] text-[#8fa9a1]">{group.label}</div>
            {group.children?.map((child) => {
              const ChildIcon = child.icon;
              const childActive = active(path, child.href);
              return (
                <Link
                  key={child.href}
                  href={child.href}
                  role="menuitem"
                  onClick={() => {
                    compactMenu.close();
                    onGo();
                  }}
                  className={`flex min-h-9 items-center gap-2.5 rounded-lg px-3 text-[12px] font-semibold transition ${childActive ? "bg-[#2b605a] text-white" : "text-[#b8cbc4] hover:bg-white/[.07] hover:text-white"}`}
                >
                  <ChildIcon size={14} />
                  {child.label}
                </Link>
              );
            })}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        aria-expanded={sectionOpen}
        className={`flex min-h-10 w-full items-center gap-3 rounded-xl px-3 text-left text-[13px] font-semibold transition ${
          isActive ? "bg-white/[.08] text-white" : "text-[#b8cbc4] hover:bg-white/[.07] hover:text-white"
        }`}
        onClick={() => setSectionOpen((value) => !value)}
      >
        <Icon size={16} />
        <span className="flex-1">{group.label}</span>
        <ChevronDown size={13} className={`transition ${sectionOpen ? "rotate-180" : ""}`} />
      </button>
      {sectionOpen ? (
        <div className="mt-1 space-y-1 pl-3">
          {group.children?.map((child) => {
            const ChildIcon = child.icon;
            const childActive = active(path, child.href);
            return (
              <Link
                key={child.href}
                href={child.href}
                onClick={onGo}
                aria-current={childActive ? "page" : undefined}
                className={`flex min-h-9 items-center gap-2.5 rounded-lg px-3 text-[12px] font-semibold transition ${
                  childActive
                    ? "bg-[#2b605a] text-white shadow-[inset_3px_0_0_#d8c56a]"
                    : "text-[#9eb5ad] hover:bg-white/[.06] hover:text-white"
                }`}
              >
                <ChildIcon size={14} />
                {child.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function ControlShell({
  children,
  title,
  subtitle,
  userEmail,
}: {
  children: ReactNode;
  title: string;
  subtitle?: string;
  userEmail?: string;
}) {
  const path = usePathname();
  const router = useRouter();
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [resolvedEmail, setResolvedEmail] = useState(userEmail || "");
  const [unread, setUnread] = useState(0);
  const quickMenu = useStablePopover();
  const accountMenu = useStablePopover();

  useEffect(() => {
    setCollapsed(window.localStorage.getItem(SIDEBAR_KEY) === "true");
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_KEY, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    quickMenu.close();
    accountMenu.close();
    setMobile(false);
  }, [accountMenu.close, path, quickMenu.close]);

  useEffect(() => {
    if (userEmail) {
      setResolvedEmail(userEmail);
      return;
    }

    let cancelled = false;
    void apiJson<Me>("/auth/me", { ttlMs: 30_000 })
      .then((data) => {
        if (!cancelled && data.email) setResolvedEmail(data.email);
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [userEmail]);

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ unread?: number }>).detail;
      if (typeof detail?.unread === "number") setUnread(detail.unread);
    };
    window.addEventListener("ithute:notifications-updated", listener);
    return () => window.removeEventListener("ithute:notifications-updated", listener);
  }, []);

  const initials = useMemo(
    () =>
      (resolvedEmail || "MD")
        .split("@")[0]
        .split(/[._-]/)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("") || "MD",
    [resolvedEmail],
  );

  async function logout() {
    accountMenu.close();
    await fetch(`${PLATFORM_API_URL}/auth/logout`, { method: "POST", credentials: "include" });
    router.replace("/login");
  }

  const side = (
    <div className="control-shell-sidebar flex h-full flex-col bg-[linear-gradient(180deg,#123a38_0%,#103532_58%,#0c2d2b_100%)] text-white">
      <div className={`border-b border-white/[.09] py-4 ${collapsed ? "px-3" : "px-4"}`}>
        <Link href="/dashboard" className={`flex items-center rounded-xl ${collapsed ? "justify-center" : "gap-3"}`} title="Mailbox DNS">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#d8c56a] text-sm font-black text-[#173c36] shadow-[0_6px_18px_rgba(0,0,0,.12)]">MD</div>
          {collapsed ? null : (
            <div>
              <p className="text-[14px] font-black tracking-[-0.01em]">Mailbox DNS</p>
              <p className="text-[9px] font-bold uppercase tracking-[.14em] text-[#8fa9a1]">!THUTE · Email · DNS · Hosting</p>
            </div>
          )}
        </Link>
      </div>

      <nav className="mailbox-sidebar-scroll flex-1 space-y-1.5 overflow-y-auto p-3">
        {navigation.map((group) => (
          <NavItem key={group.label} group={group} path={path} compact={collapsed} onGo={() => setMobile(false)} />
        ))}
      </nav>

      <div className="border-t border-white/[.09] p-3">
        <div className={`flex items-center rounded-xl border border-white/[.09] bg-white/[.055] p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,.025)] ${collapsed ? "justify-center" : "gap-2.5"}`}>
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#d8c56a] text-[11px] font-black text-[#173c36]">{initials}</div>
          {collapsed ? null : (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-bold">Platform account</p>
              <p className="truncate text-[9px] text-[#90aaa2]">{resolvedEmail || "Authenticated user"}</p>
            </div>
          )}
        </div>
        <button
          onClick={() => void logout()}
          title="Sign out"
          className={`mt-2 flex min-h-9 w-full items-center rounded-lg text-[11px] font-bold text-[#ffb4ad] transition hover:bg-red-500/[.10] ${collapsed ? "justify-center px-2" : "gap-2.5 px-3"}`}
        >
          <LogOut size={14} />
          {collapsed ? null : "Sign out"}
        </button>
      </div>
    </div>
  );

  const desktopWidth = collapsed ? "lg:w-[76px]" : "lg:w-[264px]";
  const contentPadding = collapsed ? "lg:pl-[76px]" : "lg:pl-[264px]";

  return (
    <div className="mailbox-admin-shell">
      <aside className={`fixed inset-y-0 left-0 z-40 hidden transition-[width] duration-200 lg:block ${desktopWidth}`}>{side}</aside>

      {mobile ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="Close navigation overlay" className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setMobile(false)} />
          <aside className="relative h-full w-[86%] max-w-[280px] shadow-2xl">
            <button
              aria-label="Close navigation"
              onClick={() => setMobile(false)}
              className="absolute right-3 top-3 z-10 grid h-8 w-8 place-items-center rounded-lg border border-white/[.12] bg-[#123a38] text-white"
            >
              <X size={15} />
            </button>
            {side}
          </aside>
        </div>
      ) : null}

      <div className={`control-shell-canvas min-h-screen transition-[padding] duration-200 ${contentPadding}`}>
        <header className="control-shell-topbar sticky top-0 z-30 border-b border-[#dfe7e2] bg-white/88 shadow-[0_1px_0_rgba(23,50,38,.03)] backdrop-blur-xl">
          <div className="mailbox-admin-workspace flex min-h-[68px] items-center gap-3 px-3 sm:px-4 lg:px-5">
            <button
              onClick={() => {
                if (window.innerWidth >= 1024) setCollapsed((value) => !value);
                else setMobile(true);
              }}
              className="icon-button"
              aria-label="Toggle navigation"
            >
              <Menu size={17} />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="hidden rounded-full border border-[#d9e7df] bg-[#f2f8f4] px-2 py-1 text-[8px] font-black uppercase tracking-[.13em] text-[#397164] sm:inline">!THUTE workspace</span>
                <p className="truncate text-[13px] font-black tracking-[-0.01em] text-[#21342a]">{title}</p>
              </div>
              {subtitle ? <p className="mt-0.5 truncate text-[10px] text-[#819087]">{subtitle}</p> : null}
            </div>

            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
              className="hidden min-h-9 items-center gap-2 rounded-xl border border-[#dce6e0] bg-[#f7faf8] px-3 text-[10px] font-bold text-[#718078] shadow-[0_1px_2px_rgba(23,50,38,.03)] transition hover:bg-white hover:text-[#285b55] md:flex"
              title="Search Mailbox DNS"
            >
              <Search size={14} />
              <span className="hidden xl:inline">Search</span>
              <span className="ithute-kbd">Ctrl K</span>
            </button>

            <div ref={quickMenu.rootRef} className="relative">
              <button
                ref={quickMenu.triggerRef}
                type="button"
                className="btn-secondary hidden sm:inline-flex"
                onClick={quickMenu.toggle}
                aria-haspopup="menu"
                aria-expanded={quickMenu.open}
              >
                <Plus size={14} /> Quick create
                <ChevronDown size={12} className={`transition ${quickMenu.open ? "rotate-180" : ""}`} />
              </button>
              {quickMenu.open ? (
                <div role="menu" className="ithute-dropdown-panel absolute right-0 top-12 z-[70] w-64 p-2">
                  <p className="px-3 pb-1.5 pt-1 text-[9px] font-black uppercase tracking-[0.12em] text-[#87948e]">Create resource</p>
                  <Link role="menuitem" href="/domains" className="ithute-dropdown-item" onClick={() => quickMenu.close()}>Add or verify domain</Link>
                  <Link role="menuitem" href="/mailboxes" className="ithute-dropdown-item" onClick={() => quickMenu.close()}>Create mailbox</Link>
                  <Link role="menuitem" href="/transactional-email" className="ithute-dropdown-item" onClick={() => quickMenu.close()}>Create SMTP credential</Link>
                  <Link role="menuitem" href="/support" className="ithute-dropdown-item" onClick={() => quickMenu.close()}>Open support ticket</Link>
                </div>
              ) : null}
            </div>

            <Link href="/notifications" className="icon-button relative hidden sm:grid" aria-label="Notifications">
              <Bell size={15} />
              {unread > 0 ? <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-[#b42318] px-1 text-center text-[8px] font-black leading-4 text-white">{unread > 99 ? "99+" : unread}</span> : null}
            </Link>
            <div className="hidden items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[9px] font-black uppercase tracking-[.07em] text-emerald-700 xl:flex">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" /> Platform live
            </div>

            <div ref={accountMenu.rootRef} className="relative">
              <button
                ref={accountMenu.triggerRef}
                type="button"
                onClick={accountMenu.toggle}
                aria-haspopup="menu"
                aria-expanded={accountMenu.open}
                className={`grid h-9 w-9 place-items-center rounded-xl border text-[10px] font-black shadow-sm transition ${accountMenu.open ? "border-[#285b55] bg-[#285b55] text-white" : "border-[#dce6e0] bg-white text-[#285b55] hover:border-[#a9c1b6] hover:bg-[#f4f8f6]"}`}
                title={resolvedEmail || "Platform account"}
              >
                {initials}
              </button>
              {accountMenu.open ? (
                <div role="menu" className="ithute-dropdown-panel absolute right-0 top-12 z-[70] w-[min(88vw,290px)] p-2">
                  <div className="rounded-xl bg-[linear-gradient(135deg,#123a38,#285b55)] p-3 text-white">
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8c56a] text-[11px] font-black text-[#173c36]">{initials}</div>
                      <div className="min-w-0">
                        <p className="text-[11px] font-black">Platform account</p>
                        <p className="mt-0.5 truncate text-[9px] text-white/70">{resolvedEmail || "Authenticated user"}</p>
                      </div>
                    </div>
                  </div>
                  <Link role="menuitem" href="/webmail" className="ithute-dropdown-item mt-1 flex items-center gap-2.5" onClick={() => accountMenu.close()}><Mail size={14}/>Open Webmail</Link>
                  <Link role="menuitem" href="/settings" className="ithute-dropdown-item flex items-center gap-2.5" onClick={() => accountMenu.close()}><Settings size={14}/>Account settings</Link>
                  <Link role="menuitem" href="/security" className="ithute-dropdown-item flex items-center gap-2.5" onClick={() => accountMenu.close()}><ShieldCheck size={14}/>Security</Link>
                  <div className="my-1 border-t border-[#e7ece9]" />
                  <button role="menuitem" type="button" onClick={() => void logout()} className="ithute-dropdown-item flex w-full items-center gap-2.5 text-left text-[#a33129]"><LogOut size={14}/>Sign out</button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="control-shell-stage mailbox-admin-workspace p-3 sm:p-4 lg:p-5">
          <div className="control-shell-content">{children}</div>
        </main>
      </div>
    </div>
  );
}
