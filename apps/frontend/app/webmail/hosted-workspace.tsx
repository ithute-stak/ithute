"use client";

import Link from "next/link";
import {
  Archive,
  Building2,
  BrainCircuit,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  FolderClosed,
  Forward,
  Inbox,
  LogOut,
  Mail,
  Menu,
  MoreVertical,
  Paperclip,
  PenLine,
  RefreshCw,
  Reply,
  ReplyAll,
  Search,
  Send,
  Settings2,
  ShieldAlert,
  Star,
  UsersRound,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BusinessContactWorkspace } from "./business-contact-workspace";
import { MailCompose } from "./mail-compose";
import { MailPrivacyNote } from "./mail-content";
import { MailLoading } from "./mail-loading";
import { MailSettingsPanel, resolvedTheme, useMailPreferences } from "./mail-preferences";
import {
  API,
  PAGE_SIZE,
  addressOnly,
  draftStorageKey,
  emptyCompose,
  folderKind,
  humanBytes,
  initials,
  isEditableTarget,
  senderName,
  shortDate,
  splitAddresses,
  stripHtml,
  textToHtml,
  webmail,
  type ComposeState,
  type Folder,
  type FolderCount,
  type InboxView,
  type MessageRow,
} from "./mail-types";

type SessionInfo = {
  authenticated?: boolean;
  address: string;
};

type ComposeKind = "new" | "reply" | "reply-all" | "forward";
type BusinessContact = {
  email: string;
  name?: string;
  online?: boolean;
  interactions?: number;
  last_seen?: string;
  sources?: string[];
  pinned?: boolean;
  domain?: string;
  company?: string;
};
type ConversationMessage = MessageRow & { folder?: string };
type InboxSort = "newest" | "attention" | "unread" | "starred";

function attentionScore(row: MessageRow): number {
  // Display-only, explainable heuristics. Never treat these hints as security verdicts.
  const subject = (row.subject || "").toLowerCase();
  const sender = (row.from || "").toLowerCase();
  const text = `${subject} ${row.snippet || ""}`.toLowerCase();
  let score = row.seen ? 0 : 30;
  if (row.flagged) score += 25;
  if (/\\b(urgent|action required|response needed|deadline|overdue|past due)\\b/i.test(text)) score += 30;
  if (/\\b(invoice|payment due|statement|receipt|approval|contract|verification)\\b/i.test(subject)) score += 12;
  if (/\\b(newsletter|unsubscribe|promotion|sale|discount)\\b/i.test(text)) score -= 25;
  if (/no-?reply|noreply/.test(sender)) score -= 8;
  // A recent email wins ties, but cannot outrank a significantly more actionable email.
  return score;
}

function sortInboxMessages(rows: MessageRow[], mode: InboxSort): MessageRow[] {
  return [...rows].sort((a, b) => {
    if (mode === "attention") {
      const difference = attentionScore(b) - attentionScore(a);
      if (difference) return difference;
    }
    if (mode === "unread" && a.seen !== b.seen) return a.seen ? 1 : -1;
    if (mode === "starred" && a.flagged !== b.flagged) return a.flagged ? -1 : 1;
    return (Date.parse(b.date || "") || 0) - (Date.parse(a.date || "") || 0);
  });
}

type MailIntelligence = {
  model: string;
  trust?: {
    state: string;
    verified: boolean;
    registry_match: boolean;
    sender: string;
    display_name: string;
    category: string;
    trust_reason: string;
    authentication: {
      spf: string;
      dkim: string;
      dmarc: string;
      arc: string;
      authenticated: boolean;
      any_failure: boolean;
    };
    url_intelligence: {
      count: number;
      suspicious_count: number;
      items: Array<{ url: string; host: string; trusted_domain_match: boolean; reasons: string[] }>;
    };
    explainable_score?: {
      risk_before_trust_credit: number;
      verified_trust_credit: number;
      final_phishing_score: number;
      rule: string;
    };
  };
  reputation?: {
    available?: boolean;
    combined_score?: number;
    confidence?: number;
    requested_risk_adjustment?: number;
    applied_risk_adjustment?: number;
    negative_credit_suppressed?: boolean;
    sender?: { score?: number; state?: string; confidence?: number; observations?: number };
    domain?: { name?: string; score?: number; state?: string; confidence?: number; observations?: number; domain_age_days?: number | null; identity_status?: string; enrichment_source?: string | null };
    privacy?: { sender_address_stored?: boolean; sender_hash_algorithm?: string; raw_message_content_stored?: boolean };
    rule?: string;
  };
  security: {
    phishing_probability: number;
    bec_probability: number;
    recommended_action: "allow" | "review" | "warn_and_verify";
    signals: Array<{ signal: string; weight: number; evidence: string[] }>;
  };
  business: {
    intent: { label: string; confidence: number; alternatives?: Array<{ label: string; score: number }>; evidence?: string[] };
    priority: "low" | "normal" | "high" | "critical";
    priority_score: number;
    reply_needed: boolean;
    reply_evidence?: { question_mark: boolean; request_terms: string[] };
    entities: {
      emails: string[];
      urls: string[];
      money: string[];
      dates: string[];
      references: string[];
      deadline_terms: string[];
    };
    summary: string;
  };
  behavior?: {
    score: number;
    state: "stable" | "watch" | "elevated" | "high";
    confidence: number;
    observations: number;
    signals: Array<{ signal: string; weight: number; hour_utc?: number; reply_domain?: string; known_reply_domains?: string[] }>;
  };
  supervised_shadow?: {
    available?: boolean;
    model_id?: string;
    version?: string;
    lifecycle_state?: string;
    probabilities?: { legitimate?: number; phishing?: number; bec?: number };
    baseline?: { legitimate?: number; phishing?: number; bec?: number };
    latency_ms?: number | null;
    shadow_only?: boolean;
    canary_applied?: boolean;
    baseline_preserved?: boolean;
    effective_security?: {
      phishing_probability: number;
      bec_probability: number;
      recommended_action: string;
    } | null;
    active_champion?: {
      model_id: string;
      version: string;
      probabilities: { legitimate?: number; phishing?: number; bec?: number };
      latency_ms?: number | null;
    } | null;
    fallback?: string;
  };
  governance: {
    automatic_blocking: boolean;
    training_use: boolean;
    explainable: boolean;
  };
};
type IntelligentMessage = MessageRow & { intelligence?: MailIntelligence };

function folderIcon(name: string) {
  const kind = folderKind(name);
  if (kind === "inbox") return <Inbox size={17} />;
  if (kind === "sent") return <Send size={17} />;
  if (kind === "drafts") return <FileText size={17} />;
  if (kind === "trash") return <Trash2 size={17} />;
  if (kind === "archive") return <Archive size={17} />;
  return <FolderClosed size={17} />;
}

function folderDestination(folders: Folder[], kind: "archive" | "trash") {
  const names = folders.map((item) => item.name);
  const preferred = kind === "archive" ? ["Archive", "All Mail"] : ["Trash", "Deleted Items", "Deleted"];
  return preferred.find((name) => names.some((candidate) => candidate.toLowerCase() === name.toLowerCase())) || preferred[0];
}

function hasComposeContent(compose: ComposeState) {
  return Boolean(
    compose.to.trim() || compose.cc.trim() || compose.bcc.trim() || compose.subject.trim() ||
    compose.bodyText.trim() || compose.bodyHtml.trim() || compose.attachments.length,
  );
}

function normalizedRecipients(value: string) {
  return splitAddresses(value).map(addressOnly).filter(Boolean);
}

function unique(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function quoteForReply(row: MessageRow) {
  const source = row.body_text || row.snippet || "";
  const header = `On ${row.date || "an earlier date"}, ${row.from} wrote:`;
  return {
    text: `\n\n${header}\n${source.split("\n").map((line) => `> ${line}`).join("\n")}`,
    html: `<br><br><div style="color:#64748b;font-size:12px">${textToHtml(header)}</div><blockquote style="margin:8px 0 0 0;border-left:3px solid #cbd5e1;padding-left:12px;color:#64748b">${textToHtml(source)}</blockquote>`,
  };
}

function quoteForForward(row: MessageRow) {
  const source = row.body_text || row.snippet || "";
  const header = `---------- Forwarded message ----------\nFrom: ${row.from}\nDate: ${row.date}\nSubject: ${row.subject}\nTo: ${row.to}${row.cc ? `\nCc: ${row.cc}` : ""}`;
  return {
    text: `\n\n${header}\n\n${source}`,
    html: `<br><br><div style="border-top:1px solid #d7dee8;padding-top:14px;color:#64748b;font-size:12px;line-height:1.65">${textToHtml(header)}</div><div style="margin-top:14px">${textToHtml(source)}</div>`,
  };
}

type ThreadGroup = {
  key: string;
  messages: MessageRow[];
  latest: MessageRow;
  unreadCount: number;
  flagged: boolean;
  attachmentCount: number;
  senderLabels: string[];
};

function normalizedThreadSubject(row: MessageRow) {
  if (row.thread?.subject_key) return row.thread.subject_key;
  let subject = String(row.subject || "").trim().toLowerCase();
  let previous = "";
  while (subject && subject !== previous) {
    previous = subject;
    subject = subject.replace(/^(?:(?:re|fw|fwd)\s*:\s*)+/i, "").replace(/^\[(?:external|ext|spam|bulk)\]\s*/i, "").trim();
  }
  return subject;
}

function rowParticipants(row: MessageRow) {
  const values = [row.from, row.to, row.cc]
    .flatMap((value) => splitAddresses(String(value || "")))
    .map((value) => addressOnly(value).toLowerCase())
    .filter(Boolean);
  return new Set(values);
}

function participantsOverlap(left: MessageRow, right: MessageRow) {
  const a = rowParticipants(left);
  const b = rowParticipants(right);
  for (const value of a) if (b.has(value)) return true;
  return false;
}

function subjectFallbackEligible(left: MessageRow, right: MessageRow) {
  if (!participantsOverlap(left, right)) return false;
  const leftTime = new Date(left.date || 0).getTime();
  const rightTime = new Date(right.date || 0).getTime();
  if (!Number.isFinite(leftTime) || !Number.isFinite(rightTime)) return false;
  return Math.abs(leftTime - rightTime) <= 14 * 24 * 60 * 60 * 1000;
}

function threadGroups(rows: MessageRow[]): ThreadGroup[] {
  const parent = rows.map((_, index) => index);
  const find = (index: number): number => {
    if (parent[index] !== index) parent[index] = find(parent[index]);
    return parent[index];
  };
  const union = (left: number, right: number) => {
    const a = find(left);
    const b = find(right);
    if (a !== b) parent[b] = a;
  };

  const tokenOwners = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const tokens = [
      ...(row.thread?.message_id_tokens || []),
      ...(row.thread?.in_reply_to_tokens || []),
      ...(row.thread?.reference_tokens || []),
    ];
    for (const token of new Set(tokens)) {
      const owners = tokenOwners.get(token) || [];
      for (const owner of owners) union(index, owner);
      owners.push(index);
      tokenOwners.set(token, owners);
    }
  });

  const bySubject = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const key = normalizedThreadSubject(row);
    if (!key || key === "(no subject)") return;
    const candidates = bySubject.get(key) || [];
    for (const other of candidates) {
      if (subjectFallbackEligible(row, rows[other])) union(index, other);
    }
    candidates.push(index);
    bySubject.set(key, candidates);
  });

  const grouped = new Map<number, MessageRow[]>();
  rows.forEach((row, index) => {
    const root = find(index);
    const group = grouped.get(root) || [];
    group.push(row);
    grouped.set(root, group);
  });

  return Array.from(grouped.entries()).map(([root, messages]) => {
    const ordered = [...messages].sort((a, b) => {
      const left = new Date(a.date || 0).getTime();
      const right = new Date(b.date || 0).getTime();
      return right - left;
    });
    const latest = ordered[0];
    const senders = Array.from(new Set(ordered.map((row) => senderName(row.from)).filter(Boolean))).slice(0, 3);
    return {
      key: latest.thread?.reference_tokens?.[0] || latest.thread?.in_reply_to_tokens?.[0] || latest.thread?.message_id_tokens?.[0] || `thread-${root}-${latest.uid}`,
      messages: ordered,
      latest,
      unreadCount: ordered.filter((row) => !row.seen).length,
      flagged: ordered.some((row) => row.flagged),
      attachmentCount: ordered.reduce((sum, row) => sum + (row.attachments?.length || 0), 0),
      senderLabels: senders,
    };
  }).sort((a, b) => new Date(b.latest.date || 0).getTime() - new Date(a.latest.date || 0).getTime());
}


export function HostedMailWorkspace() {
  const { preferences, setPreferences, resetPreferences, ready: preferencesReady } = useMailPreferences();
  const searchRef = useRef<HTMLInputElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [loading, setLoading] = useState(false);
  const [messageLoading, setMessageLoading] = useState(false);
  const [verdictSaving, setVerdictSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mobileFolders, setMobileFolders] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [threadedView, setThreadedView] = useState(true);
  const [inboxSort, setInboxSort] = useState<InboxSort>("newest");
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [onlyAttachments, setOnlyAttachments] = useState(false);

  const [displayName, setDisplayName] = useState("");
  const [displayNameDraft, setDisplayNameDraft] = useState("");
  const [signatureHtml, setSignatureHtml] = useState("");
  const [signatureDraft, setSignatureDraft] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);

  const [folders, setFolders] = useState<Folder[]>([]);
  const [counts, setCounts] = useState<FolderCount[]>([]);
  const [folder, setFolder] = useState("INBOX");
  const [messages, setMessages] = useState<MessageRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [inboxView, setInboxView] = useState<InboxView>("primary");
  const [businessContacts, setBusinessContacts] = useState<BusinessContact[]>([]);
  const [activeBusinessContact, setActiveBusinessContact] = useState("");

  const [composeOpen, setComposeOpen] = useState(false);
  const [composeKind, setComposeKind] = useState<ComposeKind>("new");
  const [compose, setCompose] = useState<ComposeState>(emptyCompose);
  const [composeMinimized, setComposeMinimized] = useState(false);
  const [composeExpanded, setComposeExpanded] = useState(false);
  const [showCcBcc, setShowCcBcc] = useState(false);

  const theme = resolvedTheme(preferences.theme);
  const address = session?.address || "";

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.dataset.imailTheme = theme;
  }, [theme]);

  const loadFolders = useCallback(async () => {
    const response = await webmail("/folders");
    if (response.status === 401) { window.location.assign("/webmail"); return; }
    if (response.ok) setFolders((await response.json()).items || []);
  }, []);

  const loadCounts = useCallback(async () => {
    const response = await webmail("/folder-counts");
    if (response.status === 401) { window.location.assign("/webmail"); return; }
    if (response.ok) setCounts((await response.json()).items || []);
  }, []);

  const loadIdentity = useCallback(async () => {
    const response = await webmail("/identity");
    if (!response.ok) return;
    const value = String((await response.json()).display_name || "");
    setDisplayName(value);
    setDisplayNameDraft(value);
  }, []);

  const loadSignature = useCallback(async () => {
    const response = await webmail("/signature");
    if (!response.ok) return;
    const value = String((await response.json()).html || "");
    setSignatureHtml(value);
    setSignatureDraft(value);
  }, []);

  const loadBusinessContacts = useCallback(async () => {
    try {
      const response = await webmail("/business-contacts?limit=10");
      if (!response.ok) return;
      const payload = await response.json();
      setBusinessContacts((payload.items || []) as BusinessContact[]);
    } catch {
      // Presence/contact enrichment is helpful but must never block mailbox use.
    }
  }, []);

  const loadMessages = useCallback(async (target: string, search = "", nextOffset = 0) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ folder: target, limit: String(PAGE_SIZE), offset: String(nextOffset) });
      if (search.trim()) params.set("q", search.trim());
      const response = await webmail(`/messages?${params}`);
      if (response.status === 401) { window.location.assign("/webmail"); return [] as MessageRow[]; }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load messages");
      const payload = await response.json();
      const items = (payload.items || []) as MessageRow[];
      setMessages(items);
      setTotal(Number(payload.total || 0));
      setOffset(nextOffset);
      setSelectedUids(new Set());
      return items;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load messages");
      return [] as MessageRow[];
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([loadFolders(), loadCounts(), loadMessages(folder, query, offset), loadBusinessContacts()]);
  }, [folder, loadBusinessContacts, loadCounts, loadFolders, loadMessages, offset, query]);

  async function openMessageByUid(uid: string, targetFolder: string, pushHistory: boolean, preview?: MessageRow) {
    if (preview) setSelected(preview);
    setMessageLoading(true);
    setError("");
    if (pushHistory) {
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("folder", targetFolder);
      url.searchParams.set("message", uid);
      window.history.pushState({ folder: targetFolder, message: uid }, "", `${url.pathname}?${url.searchParams}`);
    }
    try {
      const response = await webmail(`/messages/${uid}?folder=${encodeURIComponent(targetFolder)}`);
      if (response.status === 401) { window.location.assign("/webmail"); return; }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to open message");
      const full = (await response.json()) as IntelligentMessage;
      setSelected(full);
      setMessages((items) => items.map((item) => item.uid === uid ? { ...item, seen: true } : item));
      void loadCounts();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open message");
    } finally {
      setMessageLoading(false);
    }
  }

  async function openMessage(row: MessageRow) {
    const targetFolder = (row as ConversationMessage).folder || folder;
    await openMessageByUid(row.uid, targetFolder, true, row);
  }

  async function saveIntelligenceVerdict(label: "legitimate" | "phishing" | "bec") {
    if (!selected) return;
    setVerdictSaving(true);
    setError("");
    try {
      const targetFolder = (selected as ConversationMessage).folder || folder;
      const response = await webmail(`/messages/${selected.uid}/intelligence/verdict?folder=${encodeURIComponent(targetFolder)}`, {
        method: "POST",
        body: JSON.stringify({ label, confidence: 0.95 }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(payload.detail || "Unable to save intelligence verdict"));
      setNotice(`Mail Intelligence verdict saved: ${label}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save intelligence verdict");
    } finally {
      setVerdictSaving(false);
    }
  }

  async function openBusinessContact(contact: BusinessContact) {
    setLoading(true);
    setError("");
    setSelected(null);
    setActiveBusinessContact(contact.email);
    setMobileFolders(false);
    try {
      const response = await webmail(`/business-conversation?email=${encodeURIComponent(contact.email)}&limit=40`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load conversation history");
      const payload = await response.json();
      const items = (payload.items || []) as ConversationMessage[];
      setMessages(items);
      setTotal(items.length);
      setOffset(0);
      setFolder("INBOX");
      setQuery(contact.email);
      setInboxView("primary");
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("folder", "INBOX");
      url.searchParams.set("q", contact.email);
      window.history.pushState({ folder: "INBOX", q: contact.email }, "", `${url.pathname}?${url.searchParams}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load conversation history");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const sessionResponse = await webmail("/session");
        if (!active) return;
        if (!sessionResponse.ok) { window.location.assign("/webmail"); return; }
        const sessionData = (await sessionResponse.json()) as SessionInfo;
        setSession(sessionData);

        const params = new URLSearchParams(window.location.search);
        const initialFolder = params.get("folder") || "INBOX";
        const initialQuery = params.get("q") || "";
        const initialMessage = params.get("message") || "";
        setFolder(initialFolder);
        setQuery(initialQuery);

        await Promise.all([loadFolders(), loadCounts(), loadIdentity(), loadSignature(), loadBusinessContacts()]);
        const items = await loadMessages(initialFolder, initialQuery, 0);
        if (!active) return;
        if (initialMessage) {
          const preview = items.find((item) => item.uid === initialMessage);
          await openMessageByUid(initialMessage, initialFolder, false, preview);
        }
      } catch {
        if (active) setError("The mailbox could not be opened. Please refresh and try again.");
      } finally {
        if (active) setChecking(false);
      }
    })();
    return () => { active = false; };
  }, [loadBusinessContacts, loadCounts, loadFolders, loadIdentity, loadMessages, loadSignature]);

  useEffect(() => {
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search);
      const nextFolder = params.get("folder") || "INBOX";
      const nextMessage = params.get("message") || "";
      const nextQuery = params.get("q") || "";
      if (nextFolder !== folder || nextQuery !== query) {
        setFolder(nextFolder);
        setQuery(nextQuery);
        setInboxView("primary");
        void loadMessages(nextFolder, nextQuery, 0).then((items) => {
          if (nextMessage) void openMessageByUid(nextMessage, nextFolder, false, items.find((item) => item.uid === nextMessage));
          else setSelected(null);
        });
      } else if (nextMessage) {
        void openMessageByUid(nextMessage, nextFolder, false, messages.find((item) => item.uid === nextMessage));
      } else {
        setSelected(null);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [folder, loadMessages, messages, query]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // Authenticated server-sent mailbox events trigger immediate lightweight reconciliation.
  // The existing visible-tab poll remains a fallback when streaming is unavailable.
  useEffect(() => {
    if (!session?.authenticated || typeof EventSource === "undefined") return;
    let active = true;
    let debounce: number | undefined;
    let pending = false;
    const source = new EventSource(`${API}/webmail/events/stream`, { withCredentials: true });
    const reconcile = async () => {
      if (!active || pending || document.visibilityState !== "visible") return;
      pending = true;
      try {
        const params = new URLSearchParams({ folder, limit: String(PAGE_SIZE), offset: String(offset) });
        if (query.trim()) params.set("q", query.trim());
        const response = await webmail(`/messages?${params}`);
        if (!response.ok || !active) return;
        const payload = await response.json();
        if (!active) return;
        const incoming = (payload.items || []) as MessageRow[];
        setMessages(previous => previous.length === incoming.length && previous.every((row, index) =>
          row.uid === incoming[index]?.uid && row.seen === incoming[index]?.seen &&
          row.flagged === incoming[index]?.flagged && row.subject === incoming[index]?.subject &&
          row.snippet === incoming[index]?.snippet && row.date === incoming[index]?.date
        ) ? previous : incoming);
        setTotal(Number(payload.total || 0));
        void loadCounts();
      } catch {
        // Poll-based reconciliation remains active if live updates fail.
      } finally {
        pending = false;
      }
    };
    const onChange = () => {
      if (debounce !== undefined) window.clearTimeout(debounce);
      debounce = window.setTimeout(() => void reconcile(), 300);
    };
    source.addEventListener("mailbox.changed", onChange);
    source.addEventListener("flags_changed", onChange);
    source.addEventListener("message_moved", onChange);
    source.addEventListener("message_deleted", onChange);
    source.addEventListener("changed", onChange);
    return () => {
      active = false;
      if (debounce !== undefined) window.clearTimeout(debounce);
      source.close();
    };
  }, [session?.authenticated, folder, query, offset, loadCounts]);

  // Reconcile the currently visible page without clearing selection or interrupting a reader.
  // Polling is a fallback transport until the mailbox server exposes authenticated
  // durable change events. Pause when hidden to avoid unnecessary network activity.
  useEffect(() => {
    if (!session?.authenticated) return;
    let cancelled = false;
    let busy = false;
    const reconcile = async () => {
      if (cancelled || busy || document.visibilityState !== "visible") return;
      busy = true;
      try {
        const params = new URLSearchParams({ folder, limit: String(PAGE_SIZE), offset: String(offset) });
        if (query.trim()) params.set("q", query.trim());
        const response = await webmail(`/messages?${params}`);
        if (!response.ok || cancelled) return;
        const payload = await response.json();
        if (cancelled) return;
        const incoming = (payload.items || []) as MessageRow[];
        setMessages((previous) => {
          if (previous.length === incoming.length && previous.every((row, index) =>
            row.uid === incoming[index]?.uid &&
            row.seen === incoming[index]?.seen &&
            row.flagged === incoming[index]?.flagged &&
            row.subject === incoming[index]?.subject &&
            row.snippet === incoming[index]?.snippet &&
            row.date === incoming[index]?.date
          )) return previous;
          return incoming;
        });
        setTotal(Number(payload.total || 0));
        void loadCounts();
      } catch {
        // A transient sync failure must never block reading or editing mail.
      } finally {
        busy = false;
      }
    };
    const interval = window.setInterval(() => void reconcile(), 30000);
    const onVisible = () => { if (document.visibilityState === "visible") void reconcile(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [session?.authenticated, folder, query, offset, loadCounts]);

  useEffect(() => {
    const refreshContacts = () => void loadBusinessContacts();
    const timer = window.setInterval(refreshContacts, 45000);
    window.addEventListener("ithute:mailbox-refreshed", refreshContacts);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("ithute:mailbox-refreshed", refreshContacts);
    };
  }, [loadBusinessContacts]);

  useEffect(() => {
    if (!composeOpen || !address) return;
    const timer = window.setTimeout(() => {
      try {
        const key = draftStorageKey(address);
        if (hasComposeContent(compose)) window.localStorage.setItem(key, JSON.stringify(compose));
        else window.localStorage.removeItem(key);
      } catch {
        // Browser storage can be unavailable; the open composer still works.
      }
    }, 550);
    return () => window.clearTimeout(timer);
  }, [address, compose, composeOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "/") { event.preventDefault(); searchRef.current?.focus(); }
      else if (key === "c") { event.preventDefault(); startNew(); }
      else if (key === "r" && selected) { event.preventDefault(); startReply(selected); }
      else if (key === "f" && selected) { event.preventDefault(); startForward(selected); }
      else if (event.key === "Escape" && selected) { event.preventDefault(); closeReader(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  function countFor(name: string) {
    const row = counts.find((item) => item.name.toLowerCase() === name.toLowerCase());
    if (!row) return 0;
    return folderKind(name) === "inbox" ? row.unseen : row.messages;
  }

  function closeReader() {
    setSelected(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("message");
    window.history.pushState({ folder }, "", `${url.pathname}?${url.searchParams}`);
  }

  function openFolder(name: string, view: InboxView = "primary") {
    setFolder(name);
    setInboxView(view);
    setQuery("");
    setOnlyUnread(false);
    setOnlyAttachments(false);
    setSelected(null);
    setSelectedUids(new Set());
    setActiveBusinessContact("");
    setMobileFolders(false);
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("folder", name);
    window.history.pushState({ folder: name }, "", `${url.pathname}?${url.searchParams}`);
    void loadMessages(name, "", 0);
  }

  function openVirtualView(view: InboxView) {
    if (folder !== "INBOX") {
      setFolder("INBOX");
      void loadMessages("INBOX", "", 0);
    }
    setInboxView(view);
    setSelected(null);
    setSelectedUids(new Set());
    setMobileFolders(false);
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("folder", "INBOX");
    window.history.pushState({ folder: "INBOX", view }, "", `${url.pathname}?${url.searchParams}`);
  }

  async function setRowFlags(row: MessageRow, payload: { seen?: boolean; flagged?: boolean }) {
    const response = await webmail(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify(payload) });
    if (!response.ok) return;
    setMessages((items) => items.map((item) => item.uid === row.uid ? { ...item, ...payload } : item));
    if (selected?.uid === row.uid) setSelected((current) => current ? { ...current, ...payload } : current);
    if (payload.seen !== undefined) void loadCounts();
  }

  async function moveRow(row: MessageRow, destination: string) {
    const response = await webmail(`/messages/${row.uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) });
    if (!response.ok) { setError((await response.json().catch(() => ({}))).detail || "Unable to move message"); return; }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    setSelectedUids((current) => { const next = new Set(current); next.delete(row.uid); return next; });
    if (selected?.uid === row.uid) closeReader();
    setNotice(destination.toLowerCase().includes("archive") ? "Conversation archived" : `Moved to ${destination}`);
    void loadCounts();
  }

  async function deleteRow(row: MessageRow) {
    const response = await webmail(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" });
    if (!response.ok) { setError((await response.json().catch(() => ({}))).detail || "Unable to delete message"); return; }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    setSelectedUids((current) => { const next = new Set(current); next.delete(row.uid); return next; });
    if (selected?.uid === row.uid) closeReader();
    setNotice(folderKind(folder) === "trash" ? "Message deleted permanently" : "Moved to Trash");
    void loadCounts();
  }

  function toggleSelection(uid: string) {
    setSelectedUids((current) => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
      return next;
    });
  }

  async function bulkFlags(payload: { seen?: boolean; flagged?: boolean }) {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify(payload) })));
    setSelectedUids(new Set());
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  async function bulkMove(destination: string) {
    if (!selectedUids.size) return;
    const size = selectedUids.size;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) })));
    setSelectedUids(new Set());
    setNotice(`Moved ${size} message${size === 1 ? "" : "s"}`);
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  function toggleThreadSelection(thread: ThreadGroup) {
    setSelectedUids((current) => {
      const next = new Set(current);
      const allSelected = thread.messages.every((row) => next.has(row.uid));
      for (const row of thread.messages) {
        if (allSelected) next.delete(row.uid);
        else next.add(row.uid);
      }
      return next;
    });
  }

  async function setThreadFlags(thread: ThreadGroup, payload: { seen?: boolean; flagged?: boolean }) {
    await Promise.all(
      thread.messages.map((row) =>
        webmail(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        }),
      ),
    );
    setMessages((items) =>
      items.map((item) =>
        thread.messages.some((row) => row.uid === item.uid) ? { ...item, ...payload } : item,
      ),
    );
    if (payload.seen !== undefined) void loadCounts();
  }

  function toggleThreadExpanded(key: string) {
    setExpandedThreads((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function bulkDelete() {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" })));
    setSelectedUids(new Set());
    setNotice("Messages moved to Trash");
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  function openComposer(kind: ComposeKind, next: ComposeState) {
    setComposeKind(kind);
    setCompose(next);
    setShowCcBcc(Boolean(next.cc || next.bcc));
    setComposeMinimized(false);
    setComposeExpanded(preferences.composeFullscreen);
    setComposeOpen(true);
  }

  function composeTo(email: string) {
    openComposer("new", { ...emptyCompose, to: email, attachments: [] });
  }

  function startNew() {
    let next = { ...emptyCompose, attachments: [] } as ComposeState;
    if (address) {
      try {
        const stored = window.localStorage.getItem(draftStorageKey(address));
        if (stored) {
          next = { ...next, ...JSON.parse(stored) };
          setNotice("Restored your unfinished draft");
        }
      } catch {
        // Ignore malformed local draft data.
      }
    }
    openComposer("new", next);
  }

  function startReply(row: MessageRow) {
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    openComposer("reply", { ...emptyCompose, to: addressOnly(row.reply_to || row.from), subject, bodyText: quote.text, bodyHtml: quote.html, in_reply_to: row.message_id, references: refs, attachments: [] });
  }

  function startReplyAll(row: MessageRow) {
    const own = address.toLowerCase();
    const sender = addressOnly(row.reply_to || row.from);
    const originalTo = normalizedRecipients(row.to).filter((value) => value.toLowerCase() !== own);
    const originalCc = normalizedRecipients(row.cc).filter((value) => value.toLowerCase() !== own);
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    openComposer("reply-all", { ...emptyCompose, to: unique([sender, ...originalTo]).join(", "), cc: unique(originalCc).join(", "), subject, bodyText: quote.text, bodyHtml: quote.html, in_reply_to: row.message_id, references: refs, attachments: [] });
  }

  function startForward(row: MessageRow) {
    const quote = quoteForForward(row);
    const subject = /^fwd?:/i.test(row.subject) ? row.subject : `Fwd: ${row.subject}`;
    openComposer("forward", { ...emptyCompose, subject, bodyText: quote.text, bodyHtml: quote.html, attachments: [] });
  }

  async function attachFiles(files: FileList | null) {
    if (!files) return;
    const rows: ComposeState["attachments"] = [];
    let totalBytes = compose.attachments.reduce((sum, item) => sum + Math.floor(item.content_b64.length * 0.75), 0);
    for (const file of Array.from(files)) {
      if (file.size > 10 * 1024 * 1024) { setError(`${file.name} is larger than 10 MB`); continue; }
      totalBytes += file.size;
      if (totalBytes > 15 * 1024 * 1024) { setError("Total attachment size cannot exceed 15 MB"); break; }
      const content_b64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      rows.push({ filename: file.name, content_type: file.type || "application/octet-stream", content_b64 });
    }
    setCompose((current) => ({ ...current, attachments: [...current.attachments, ...rows].slice(0, 20) }));
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await webmail("/send-rich", {
        method: "POST",
        body: JSON.stringify({
          to: splitAddresses(compose.to), cc: splitAddresses(compose.cc), bcc: splitAddresses(compose.bcc), subject: compose.subject,
          body_text: compose.bodyText || stripHtml(compose.bodyHtml), body_html: compose.bodyHtml, signature_html: signatureHtml,
          attachments: compose.attachments, in_reply_to: compose.in_reply_to, references: compose.references,
        }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to send message");
      if (address) window.localStorage.removeItem(draftStorageKey(address));
      setCompose(emptyCompose);
      setComposeOpen(false);
      setNotice("Message sent");
      await Promise.all([loadFolders(), loadCounts()]);
      if (folderKind(folder) === "sent") await loadMessages(folder, query, offset);
      if (selected && (composeKind === "reply" || composeKind === "reply-all")) setSelected((current) => current ? { ...current, answered: true } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to send message");
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    setLoading(true);
    try {
      const response = await webmail("/drafts", { method: "POST", body: JSON.stringify({ to: splitAddresses(compose.to), cc: splitAddresses(compose.cc), subject: compose.subject, body_text: compose.bodyText || stripHtml(compose.bodyHtml) }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save draft");
      if (address) window.localStorage.removeItem(draftStorageKey(address));
      setCompose(emptyCompose);
      setComposeOpen(false);
      setNotice("Draft saved");
      await Promise.all([loadFolders(), loadCounts()]);
      if (folderKind(folder) === "drafts") await loadMessages(folder, query, offset);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save draft");
    } finally {
      setLoading(false);
    }
  }

  function discardDraft() {
    if (address) window.localStorage.removeItem(draftStorageKey(address));
    setCompose(emptyCompose);
    setComposeOpen(false);
    setNotice("Draft discarded");
  }

  async function saveAccountSettings() {
    setSavingSettings(true);
    setError("");
    try {
      const [identityResponse, signatureResponse] = await Promise.all([
        webmail("/identity", { method: "PUT", body: JSON.stringify({ display_name: displayNameDraft.trim() }) }),
        webmail("/signature", { method: "PUT", body: JSON.stringify({ html: signatureDraft }) }),
      ]);
      if (!identityResponse.ok || !signatureResponse.ok) throw new Error("Unable to save mailbox settings");
      setDisplayName(displayNameDraft.trim());
      setSignatureHtml(signatureDraft);
      setNotice("Account settings saved");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save mailbox settings");
    } finally {
      setSavingSettings(false);
    }
  }

  async function logout() {
    await webmail("/session", { method: "DELETE" });
    window.location.assign("/webmail");
  }

  function downloadAttachment(item: MessageRow["attachments"][number]) {
    if (!selected) return;
    window.open(`${API}/webmail/messages/${selected.uid}/attachments/${item.index}?folder=${encodeURIComponent(folder)}`, "_blank", "noopener,noreferrer");
  }

  const visibleMessages = useMemo(() => {
    let items = messages;
    if (inboxView === "starred") items = items.filter((row) => row.flagged);
    if (inboxView === "attachments") items = items.filter((row) => row.attachments?.length);
    if (onlyUnread) items = items.filter((row) => !row.seen);
    if (onlyAttachments) items = items.filter((row) => row.attachments?.length);
    return items;
  }, [inboxView, messages, onlyAttachments, onlyUnread]);

  const sortedMessages = useMemo(() => sortInboxMessages(visibleMessages, inboxSort), [visibleMessages, inboxSort]);
  const groupedThreads = useMemo(() => threadGroups(sortedMessages), [sortedMessages]);
  const displayedThreads = threadedView && folderKind(folder) !== "drafts"
    ? [...groupedThreads].sort((a, b) => {
        if (inboxSort === "attention") return Math.max(...b.messages.map(attentionScore)) - Math.max(...a.messages.map(attentionScore)) || (Date.parse(b.latest.date || "") || 0) - (Date.parse(a.latest.date || "") || 0);
        if (inboxSort === "unread") return b.unreadCount - a.unreadCount || (Date.parse(b.latest.date || "") || 0) - (Date.parse(a.latest.date || "") || 0);
        if (inboxSort === "starred") return Number(b.flagged) - Number(a.flagged) || (Date.parse(b.latest.date || "") || 0) - (Date.parse(a.latest.date || "") || 0);
        return 0;
      })
    : sortedMessages.map((row, index) => ({
        key: `message-${row.uid}-${index}`,
        messages: [row],
        latest: row,
        unreadCount: row.seen ? 0 : 1,
        flagged: row.flagged,
        attachmentCount: row.attachments?.length || 0,
        senderLabels: [senderName(row.from)],
      }));

  const contactGroups = useMemo(() => {
    const grouped = new Map<string, BusinessContact[]>();
    for (const contact of businessContacts) {
      const domain = contact.company || contact.domain || contact.email.split("@")[1] || "Other";
      const rows = grouped.get(domain) || [];
      rows.push(contact);
      grouped.set(domain, rows);
    }
    return Array.from(grouped.entries());
  }, [businessContacts]);

  const allVisibleSelected = visibleMessages.length > 0 && visibleMessages.every((row) => selectedUids.has(row.uid));
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + messages.length, total);
  const archiveFolder = folderDestination(folders, "archive");
  const densityClass = preferences.density === "compact" ? "py-2" : "py-3.5";
  const paneRight = preferences.readingPane === "right";
  const paneBottom = preferences.readingPane === "bottom";
  const noPane = preferences.readingPane === "none";
  const fontSize = preferences.fontScale === "small" ? "13px" : preferences.fontScale === "large" ? "16px" : "14px";

  function toggleSelectAll() {
    if (allVisibleSelected) setSelectedUids(new Set());
    else setSelectedUids(new Set(visibleMessages.map((row) => row.uid)));
  }

  if (checking || !preferencesReady || !session) {
    return <MailLoading label="Opening iMail" detail="Preparing your hosted business mailbox" />;
  }

  const relationshipWorkspace = activeBusinessContact ? (
    <BusinessContactWorkspace
      email={activeBusinessContact}
      mailboxAddress={address}
      onClose={() => { setActiveBusinessContact(""); setQuery(""); void loadMessages(folder, "", 0); }}
      onCompose={composeTo}
      onOpenMessage={(row) => void openMessage(row)}
      onChanged={() => void loadBusinessContacts()}
    />
  ) : null;

  const selectedIntelligence = (selected as IntelligentMessage | null)?.intelligence || null;
  const intelligenceTone = selectedIntelligence?.security.recommended_action === "warn_and_verify"
    ? "border-red-200 bg-red-50 text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-100"
    : selectedIntelligence?.security.recommended_action === "review"
      ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"
      : "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100";

  const reader = selected ? (
    <section className="flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-900">
      <div className="flex h-13 shrink-0 items-center gap-1 border-b border-slate-200 px-3 dark:border-white/10 sm:px-4">
        <button type="button" onClick={closeReader} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Back to inbox"><ArrowLeft size={18} /></button>
        <button type="button" onClick={() => void setRowFlags(selected, { flagged: !selected.flagged })} className={`grid h-9 w-9 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10 ${selected.flagged ? "text-amber-500" : "text-slate-500"}`} title="Star"><Star size={18} fill={selected.flagged ? "currentColor" : "none"} /></button>
        <button type="button" onClick={() => void setRowFlags(selected, { seen: !selected.seen })} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title={selected.seen ? "Mark unread" : "Mark read"}><Mail size={18} /></button>
        <button type="button" onClick={() => void moveRow(selected, archiveFolder)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Archive"><Archive size={18} /></button>
        <button type="button" onClick={() => void deleteRow(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Delete"><Trash2 size={18} /></button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button type="button" onClick={() => startReply(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply"><Reply size={18} /></button>
        <button type="button" onClick={() => startReplyAll(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply all"><ReplyAll size={18} /></button>
        <button type="button" onClick={() => startForward(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Forward"><Forward size={18} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-7 sm:py-7 lg:px-9">
        {messageLoading ? <div className="py-12"><MailLoading compact label="Opening message" detail="Loading the full message securely" /></div> : (
          <article className="imail-message-reader mx-auto max-w-4xl">
            <h1 className="pr-4 text-[22px] font-black leading-tight tracking-tight text-slate-900 dark:text-white sm:text-[26px]">{selected.subject || "(no subject)"}</h1>
            <div className="mt-6 flex items-start gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-sm font-black text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200">{initials(selected.from)}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2"><span className="font-black text-slate-900 dark:text-white">{senderName(selected.from)}</span><span className="truncate text-xs text-slate-500">&lt;{addressOnly(selected.from)}&gt;</span></div>
                <p className="mt-1 text-xs text-slate-500">to {selected.to || address}{selected.cc ? ` • cc ${selected.cc}` : ""}</p>
              </div>
              <time className="shrink-0 text-xs font-medium text-slate-500">{selected.date ? shortDate(selected.date) : ""}</time>
            </div>

            <div className="mt-5"><MailPrivacyNote /></div>
            {selectedIntelligence ? (
              <details className={`group mt-4 rounded-2xl border ${intelligenceTone}`}>
                <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/70 shadow-sm dark:bg-white/10"><BrainCircuit size={18} /></span>
                  <div className="min-w-0 flex-1"><p className="text-[10px] font-black uppercase tracking-[.12em]">Ithute Mail Intelligence</p><p className="truncate text-xs font-bold">{selectedIntelligence.business.summary}</p></div>
                  <span className="rounded-full bg-white/70 px-2.5 py-1 text-[9px] font-black uppercase dark:bg-white/10">{selectedIntelligence.security.recommended_action.replaceAll("_", " ")}</span>
                  <ChevronRight size={16} className="shrink-0 transition group-open:rotate-90" />
                </summary>
                <section className="border-t border-current/10 px-4 pb-4 pt-3">

                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/70 shadow-sm dark:bg-white/10"><BrainCircuit size={18} /></span>
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[.12em]">Ithute Mail Intelligence</p>
                      <p className="mt-1 text-sm font-black">{selectedIntelligence.business.summary}</p>
                      <p className="mt-1 text-[11px] opacity-75">Explainable analysis only — this model does not automatically block mail or use message content for training.</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <span className="rounded-full bg-white/70 px-3 py-1 text-[10px] font-black uppercase dark:bg-white/10">{selectedIntelligence.business.priority} priority</span>
                    <span className="rounded-full bg-white/70 px-3 py-1 text-[10px] font-black uppercase dark:bg-white/10">{selectedIntelligence.business.intent.label.replaceAll("_", " ")}</span>
                    {selectedIntelligence.business.reply_needed ? <span className="rounded-full bg-white/70 px-3 py-1 text-[10px] font-black uppercase dark:bg-white/10">Reply likely</span> : null}
                  </div>
                </div>

                {selectedIntelligence.trust?.registry_match ? (
                  <div className={`mt-4 rounded-2xl border p-3.5 ${selectedIntelligence.trust.verified ? "border-emerald-300/70 bg-emerald-50/80 text-emerald-950 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-50" : "border-amber-300/70 bg-amber-50/80 text-amber-950 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-50"}`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-[.12em]">{selectedIntelligence.trust.verified ? "Verified Ithute system sender" : "Ithute sender identity requires verification"}</p>
                        <p className="mt-1 text-[12px] font-black">{selectedIntelligence.trust.display_name || selectedIntelligence.trust.sender}</p>
                        <p className="mt-1 text-[10px] opacity-75">{selectedIntelligence.trust.trust_reason}</p>
                      </div>
                      <span className="rounded-full bg-white/75 px-2.5 py-1 text-[9px] font-black uppercase dark:bg-white/10">{selectedIntelligence.trust.state.replaceAll("_", " ")}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {(["spf", "dkim", "dmarc", "arc"] as const).map((mechanism) => (
                        <div key={mechanism} className="rounded-xl bg-white/75 p-2 dark:bg-white/10">
                          <p className="text-[8px] font-black uppercase opacity-60">{mechanism}</p>
                          <p className="mt-1 text-[11px] font-black uppercase">{selectedIntelligence.trust?.authentication[mechanism] || "unknown"}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[9px] font-bold">
                      <span className="rounded-lg bg-white/75 px-2.5 py-1 dark:bg-white/10">Links: {selectedIntelligence.trust.url_intelligence.count}</span>
                      <span className="rounded-lg bg-white/75 px-2.5 py-1 dark:bg-white/10">Suspicious links: {selectedIntelligence.trust.url_intelligence.suspicious_count}</span>
                      {selectedIntelligence.trust.explainable_score ? <span className="rounded-lg bg-white/75 px-2.5 py-1 dark:bg-white/10">Trust credit: -{selectedIntelligence.trust.explainable_score.verified_trust_credit}</span> : null}
                    </div>
                  </div>
                ) : null}

                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-xl bg-white/70 p-3 dark:bg-white/10">
                    <p className="text-[9px] font-black uppercase opacity-65">Phishing</p>
                    <p className="mt-1 text-xl font-black">{Math.round(selectedIntelligence.security.phishing_probability * 100)}%</p>
                  </div>
                  <div className="rounded-xl bg-white/70 p-3 dark:bg-white/10">
                    <p className="text-[9px] font-black uppercase opacity-65">BEC</p>
                    <p className="mt-1 text-xl font-black">{Math.round(selectedIntelligence.security.bec_probability * 100)}%</p>
                  </div>
                  <div className="rounded-xl bg-white/70 p-3 dark:bg-white/10">
                    <p className="text-[9px] font-black uppercase opacity-65">Intent confidence</p>
                    <p className="mt-1 text-xl font-black">{Math.round(selectedIntelligence.business.intent.confidence * 100)}%</p>
                  </div>
                  <div className="rounded-xl bg-white/70 p-3 dark:bg-white/10">
                    <p className="text-[9px] font-black uppercase opacity-65">Action</p>
                    <p className="mt-1 flex items-center gap-2 text-sm font-black"><ShieldAlert size={15} /> {selectedIntelligence.security.recommended_action.replaceAll("_", " ")}</p>
                  </div>
                </div>

                {(selectedIntelligence.business.entities.money.length || selectedIntelligence.business.entities.dates.length || selectedIntelligence.business.entities.deadline_terms.length || selectedIntelligence.business.entities.references.length) ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-bold">
                    {selectedIntelligence.business.entities.money.slice(0, 3).map((value) => <span key={`money-${value}`} className="rounded-lg bg-white/70 px-2.5 py-1 dark:bg-white/10">Amount: {value}</span>)}
                    {selectedIntelligence.business.entities.dates.slice(0, 3).map((value) => <span key={`date-${value}`} className="rounded-lg bg-white/70 px-2.5 py-1 dark:bg-white/10">Date: {value}</span>)}
                    {selectedIntelligence.business.entities.deadline_terms.slice(0, 3).map((value) => <span key={`deadline-${value}`} className="rounded-lg bg-white/70 px-2.5 py-1 dark:bg-white/10">Deadline: {value}</span>)}
                    {selectedIntelligence.business.entities.references.slice(0, 3).map((value) => <span key={`ref-${value}`} className="rounded-lg bg-white/70 px-2.5 py-1 dark:bg-white/10">Ref: {value}</span>)}
                  </div>
                ) : null}

                {selectedIntelligence.reputation?.available ? (
                  <div className="mt-3 rounded-xl bg-white/60 p-3 dark:bg-white/10">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-[.08em]">Sender reputation + domain intelligence</p>
                        <p className="mt-1 text-[11px] font-black">
                          Reputation {selectedIntelligence.reputation.combined_score ?? 50}/100 · {Math.round((selectedIntelligence.reputation.confidence ?? 0) * 100)}% confidence
                        </p>
                        <p className="mt-1 text-[9px] opacity-70">{selectedIntelligence.reputation.rule}</p>
                      </div>
                      <span className="rounded-full bg-white/70 px-2.5 py-1 text-[9px] font-black uppercase dark:bg-white/10">
                        {selectedIntelligence.reputation.applied_risk_adjustment
                          ? `${selectedIntelligence.reputation.applied_risk_adjustment > 0 ? "+" : ""}${selectedIntelligence.reputation.applied_risk_adjustment} risk`
                          : "No score adjustment"}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg bg-white/70 p-2.5 dark:bg-white/10">
                        <p className="text-[8px] font-black uppercase opacity-60">Sender history</p>
                        <p className="mt-1 text-[11px] font-black">{selectedIntelligence.reputation.sender?.state || "unknown"} · {selectedIntelligence.reputation.sender?.score ?? 50}/100</p>
                        <p className="mt-1 text-[9px] opacity-65">{selectedIntelligence.reputation.sender?.observations ?? 0} durable observation{selectedIntelligence.reputation.sender?.observations === 1 ? "" : "s"}</p>
                      </div>
                      <div className="rounded-lg bg-white/70 p-2.5 dark:bg-white/10">
                        <p className="text-[8px] font-black uppercase opacity-60">Domain intelligence</p>
                        <p className="mt-1 text-[11px] font-black">{selectedIntelligence.reputation.domain?.state || "unknown"} · {selectedIntelligence.reputation.domain?.score ?? 50}/100</p>
                        <p className="mt-1 text-[9px] opacity-65">
                          {selectedIntelligence.reputation.domain?.identity_status?.replaceAll("_", " ") || "unverified identity"}
                          {typeof selectedIntelligence.reputation.domain?.domain_age_days === "number" ? ` · ${selectedIntelligence.reputation.domain.domain_age_days} days old` : ""}
                        </p>
                      </div>
                    </div>
                    {selectedIntelligence.reputation.negative_credit_suppressed ? (
                      <p className="mt-2 rounded-lg bg-amber-50/80 px-2.5 py-2 text-[9px] font-bold text-amber-900 dark:bg-amber-400/10 dark:text-amber-100">
                        Historical trust credit was suppressed because this message has a current hard security failure.
                      </p>
                    ) : null}
                    <p className="mt-2 text-[9px] opacity-60">Reputation stores sender hashes and aggregate evidence only; raw message content is not stored in the reputation profile.</p>
                  </div>
                ) : null}

                {selectedIntelligence.behavior ? (
                  <div className="mt-3 rounded-xl bg-white/60 p-3 dark:bg-white/10">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-[.08em]">Sender behaviour</p>
                        <p className="mt-1 text-[11px] font-black">{selectedIntelligence.behavior.state.replaceAll("_", " ")} · score {selectedIntelligence.behavior.score}/100</p>
                      </div>
                      <span className="rounded-full bg-white/70 px-2.5 py-1 text-[9px] font-black dark:bg-white/10">
                        {selectedIntelligence.behavior.observations} prior observation{selectedIntelligence.behavior.observations === 1 ? "" : "s"}
                      </span>
                    </div>
                    {selectedIntelligence.behavior.signals.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedIntelligence.behavior.signals.slice(0, 5).map((signal) => (
                          <span key={signal.signal} className="rounded-lg bg-white/70 px-2.5 py-1 text-[9px] font-bold dark:bg-white/10">
                            {signal.signal.replaceAll("_", " ")} · {signal.weight > 0 ? "+" : ""}{signal.weight}
                          </span>
                        ))}
                      </div>
                    ) : <p className="mt-2 text-[10px] opacity-70">No behavioural anomaly detected for this sender.</p>}
                  </div>
                ) : null}

                {selectedIntelligence.supervised_shadow?.probabilities ? (
                  <div className="mt-3 rounded-xl bg-white/60 p-3 dark:bg-white/10">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[9px] font-black uppercase tracking-[.08em]">Supervised threat model · {selectedIntelligence.supervised_shadow.lifecycle_state || "shadow"}</p>
                        <p className="mt-1 text-[10px] opacity-75">
                          {selectedIntelligence.supervised_shadow.version || "candidate"} · {selectedIntelligence.supervised_shadow.canary_applied ? "canary may raise warnings; baseline cannot be weakened" : "does not control mail delivery"}
                        </p>
                      </div>
                      <span className="rounded-full bg-white/70 px-2.5 py-1 text-[9px] font-black uppercase dark:bg-white/10">
                        {selectedIntelligence.supervised_shadow.lifecycle_state || "shadow"}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-lg bg-white/70 p-2 dark:bg-white/10">
                        <p className="text-[8px] font-black uppercase opacity-60">Legitimate</p>
                        <p className="mt-1 text-sm font-black">{Math.round((selectedIntelligence.supervised_shadow.probabilities.legitimate ?? 0) * 100)}%</p>
                      </div>
                      <div className="rounded-lg bg-white/70 p-2 dark:bg-white/10">
                        <p className="text-[8px] font-black uppercase opacity-60">Phishing</p>
                        <p className="mt-1 text-sm font-black">{Math.round((selectedIntelligence.supervised_shadow.probabilities.phishing ?? 0) * 100)}%</p>
                      </div>
                      <div className="rounded-lg bg-white/70 p-2 dark:bg-white/10">
                        <p className="text-[8px] font-black uppercase opacity-60">BEC</p>
                        <p className="mt-1 text-sm font-black">{Math.round((selectedIntelligence.supervised_shadow.probabilities.bec ?? 0) * 100)}%</p>
                      </div>
                    </div>
                    <p className="mt-2 text-[9px] opacity-65">
                      Inference latency {typeof selectedIntelligence.supervised_shadow.latency_ms === "number" ? `${selectedIntelligence.supervised_shadow.latency_ms.toFixed(2)} ms` : "n/a"} · heuristic fallback remains active.
                    </p>
                    {selectedIntelligence.supervised_shadow.active_champion ? (
                      <p className="mt-1 text-[9px] font-bold opacity-75">
                        Active champion remains serving: {selectedIntelligence.supervised_shadow.active_champion.version}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {selectedIntelligence.security.signals.length ? (
                  <details className="mt-3 rounded-xl bg-white/60 p-3 text-[10px] dark:bg-white/10">
                    <summary className="cursor-pointer font-black uppercase tracking-[.08em]">Why the model flagged this</summary>
                    <div className="mt-2 space-y-2">
                      {selectedIntelligence.security.signals.slice(0, 6).map((signal) => (
                        <div key={signal.signal}>
                          <p className="font-black">{signal.signal.replaceAll("_", " ")} · {signal.weight > 0 ? "+" : ""}{signal.weight}</p>
                          <p className="mt-0.5 opacity-75">{signal.evidence.join(" · ")}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                ) : null}

                <div className="mt-3 border-t border-current/10 pt-3">
                  <p className="text-[9px] font-black uppercase tracking-[.08em]">Verified verdict</p>
                  <p className="mt-1 text-[10px] opacity-75">Your verdict becomes privacy-minimized training evidence. Raw message content is not stored in the learning snapshot.</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button disabled={verdictSaving} type="button" onClick={() => void saveIntelligenceVerdict("legitimate")} className="rounded-lg bg-white/70 px-3 py-1.5 text-[10px] font-black disabled:opacity-50 dark:bg-white/10">Legitimate</button>
                    <button disabled={verdictSaving} type="button" onClick={() => void saveIntelligenceVerdict("phishing")} className="rounded-lg bg-white/70 px-3 py-1.5 text-[10px] font-black disabled:opacity-50 dark:bg-white/10">Phishing</button>
                    <button disabled={verdictSaving} type="button" onClick={() => void saveIntelligenceVerdict("bec")} className="rounded-lg bg-white/70 px-3 py-1.5 text-[10px] font-black disabled:opacity-50 dark:bg-white/10">BEC</button>
                  </div>
                </div>
              </section>
              </details>
            ) : null}
            <div className="mt-6 min-h-[220px]">
              <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,.03)] dark:border-white/10 dark:bg-white/[.025]">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-2.5 text-[10px] text-slate-500 dark:border-white/10 dark:bg-white/[.025]">
                  <span className="font-black uppercase tracking-[.08em]">Message</span>
                  <div className="flex flex-wrap items-center gap-2">
                    {selected.render_contract?.kind ? <span className="rounded-full bg-white px-2 py-1 font-bold shadow-sm dark:bg-white/10">{selected.render_contract.kind.replaceAll("_", " ")}</span> : null}
                    {selected.render_contract?.density === "long" ? <span className="rounded-full bg-amber-50 px-2 py-1 font-bold text-amber-700 dark:bg-amber-400/10 dark:text-amber-200">Long message</span> : null}
                  </div>
                </div>
                <div
                  data-imail-message-body="true"
                  data-imail-sender={addressOnly(selected.from)}
                  data-imail-render-kind={selected.render_contract?.kind || "plain"}
                  className="imail-universal-body overflow-x-auto px-5 py-6 text-slate-800 dark:text-slate-100 sm:px-7"
                  style={{ fontSize }}
                >
                  {selected.body_html ? (
                    <>
                      <div
                        className="[&_a]:break-all [&_a]:font-semibold [&_a]:text-[#0b57d0] [&_a]:underline [&_blockquote]:my-4 [&_blockquote]:border-l-4 [&_blockquote]:border-slate-200 [&_blockquote]:pl-4 [&_blockquote]:text-slate-600 dark:[&_blockquote]:border-white/15 dark:[&_blockquote]:text-slate-300 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 dark:[&_code]:bg-white/10 [&_h1]:mb-4 [&_h1]:mt-6 [&_h1]:text-2xl [&_h1]:font-black [&_h2]:mb-3 [&_h2]:mt-5 [&_h2]:text-xl [&_h2]:font-black [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-lg [&_h3]:font-bold [&_hr]:my-6 [&_hr]:border-slate-200 dark:[&_hr]:border-white/10 [&_li]:my-1 [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:my-3 [&_p]:leading-7 [&_pre]:my-4 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_pre]:rounded-xl [&_pre]:bg-slate-950 [&_pre]:p-4 [&_pre]:text-slate-100 [&_table]:my-5 [&_table]:w-full [&_table]:min-w-[520px] [&_table]:border-collapse [&_td]:border [&_td]:border-slate-200 [&_td]:p-2.5 dark:[&_td]:border-white/10 [&_th]:border [&_th]:border-slate-200 [&_th]:bg-slate-50 [&_th]:p-2.5 [&_th]:text-left [&_th]:font-black dark:[&_th]:border-white/10 dark:[&_th]:bg-white/5 [&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-6"
                        dangerouslySetInnerHTML={{ __html: selected.render_contract?.conversation?.main_html || selected.body_html }}
                      />
                      {selected.render_contract?.conversation?.quoted_html ? (
                        <details className="mt-6 rounded-xl border border-slate-200 bg-slate-50/70 dark:border-white/10 dark:bg-white/[.025]">
                          <summary className="cursor-pointer list-none px-4 py-3 text-[10px] font-black uppercase tracking-[.08em] text-slate-500 [&::-webkit-details-marker]:hidden">
                            Show quoted history
                          </summary>
                          <div
                            className="border-t border-slate-200 px-4 py-4 text-sm text-slate-600 dark:border-white/10 dark:text-slate-300 [&_a]:break-all [&_a]:underline [&_blockquote]:my-3 [&_blockquote]:border-l-4 [&_blockquote]:border-slate-200 [&_blockquote]:pl-4 dark:[&_blockquote]:border-white/15"
                            dangerouslySetInnerHTML={{ __html: selected.render_contract.conversation.quoted_html }}
                          />
                        </details>
                      ) : null}
                    </>
                  ) : (
                    <>
                      <div className="whitespace-pre-wrap break-words leading-7">
                        {selected.render_contract?.conversation?.main_text || selected.body_text || selected.snippet || ""}
                      </div>
                      {selected.render_contract?.conversation?.signature_text ? (
                        <div className="mt-5 border-t border-slate-100 pt-4 text-sm text-slate-500 dark:border-white/10 dark:text-slate-400">
                          <div className="whitespace-pre-wrap break-words">{selected.render_contract.conversation.signature_text}</div>
                        </div>
                      ) : null}
                      {selected.render_contract?.conversation?.footer_text ? (
                        <details className="mt-5 rounded-xl border border-slate-200 bg-slate-50/60 dark:border-white/10 dark:bg-white/[.025]">
                          <summary className="cursor-pointer list-none px-4 py-3 text-[10px] font-black uppercase tracking-[.08em] text-slate-500 [&::-webkit-details-marker]:hidden">
                            Show footer / legal text
                          </summary>
                          <div className="whitespace-pre-wrap break-words border-t border-slate-200 px-4 py-4 text-xs leading-6 text-slate-500 dark:border-white/10 dark:text-slate-400">
                            {selected.render_contract.conversation.footer_text}
                          </div>
                        </details>
                      ) : null}
                      {selected.render_contract?.conversation?.quoted_text ? (
                        <details className="mt-5 rounded-xl border border-slate-200 bg-slate-50/70 dark:border-white/10 dark:bg-white/[.025]">
                          <summary className="cursor-pointer list-none px-4 py-3 text-[10px] font-black uppercase tracking-[.08em] text-slate-500 [&::-webkit-details-marker]:hidden">
                            Show quoted history
                          </summary>
                          <div className="whitespace-pre-wrap break-words border-t border-slate-200 px-4 py-4 text-sm leading-6 text-slate-600 dark:border-white/10 dark:text-slate-300">
                            {selected.render_contract.conversation.quoted_text}
                          </div>
                        </details>
                      ) : null}
                    </>
                  )}
                </div>
                {selected.render_contract ? (
                  <div className="border-t border-slate-100 px-4 py-2 text-[9px] font-medium text-slate-400 dark:border-white/10">
                    Safe renderer · {selected.render_contract.engines.orchestrator} orchestration · {selected.render_contract.engines.mime_structure} MIME · {selected.render_contract.engines.text_shape} text profile
                  </div>
                ) : null}
              </div>
            </div>

            {selected.attachments?.length ? (
              <div className="mt-8 border-t border-slate-200 pt-5 dark:border-white/10">
                <p className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><Paperclip size={14} /> {selected.attachments.length} attachment{selected.attachments.length === 1 ? "" : "s"}</p>
                <div className="flex flex-wrap gap-2">
                  {selected.attachments.map((item) => (
                    <button key={`${selected.uid}-${item.index}`} type="button" onClick={() => downloadAttachment(item)} className="group flex max-w-[300px] items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-left transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:bg-white/[.035] dark:hover:bg-blue-400/10">
                      <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-slate-500 shadow-sm dark:bg-white/10"><FileText size={17} /></span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-xs font-bold text-slate-800 dark:text-slate-100">{item.filename}</span><span className="block text-[10px] text-slate-500">{humanBytes(item.size || 0)}</span></span>
                      <Download size={15} className="text-slate-400 group-hover:text-[#0b57d0]" />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-9 flex flex-wrap gap-2 border-t border-slate-200 pt-5 dark:border-white/10">
              <button type="button" onClick={() => startReply(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><Reply size={16} /> Reply</button>
              <button type="button" onClick={() => startReplyAll(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><ReplyAll size={16} /> Reply all</button>
              <button type="button" onClick={() => startForward(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><Forward size={16} /> Forward</button>
            </div>
          </article>
        )}
      </div>
    </section>
  ) : (
    <section className="hidden min-h-0 flex-1 place-items-center bg-white dark:bg-slate-900 lg:grid">
      <div className="max-w-sm text-center"><span className="mx-auto grid h-16 w-16 place-items-center rounded-[22px] bg-[#eaf1fb] text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200"><Mail size={28} /></span><h2 className="mt-4 text-lg font-black text-slate-800 dark:text-white">Your message opens here</h2><p className="mt-1 text-sm leading-6 text-slate-500">Choose a message from the inbox, or change the reading pane in Settings.</p></div>
    </section>
  );

  const messageList = (
    <section className="flex min-h-0 flex-1 flex-col bg-[#f6f8f7] dark:bg-[#0e1514]">
      <div className="shrink-0 px-3 pb-2 pt-3 sm:px-4">
        <form onSubmit={(event) => { event.preventDefault(); setSelected(null); setInboxView("primary"); void loadMessages(folder, query, 0); const url = new URL(window.location.href); url.searchParams.set("folder", folder); url.searchParams.delete("message"); if (query.trim()) url.searchParams.set("q", query.trim()); else url.searchParams.delete("q"); window.history.pushState({}, "", `${url.pathname}?${url.searchParams}`); }} className="mx-auto flex h-12 max-w-4xl items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm transition focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-500/10 dark:border-white/10 dark:bg-white/[.05]">
          <Search size={18} className="shrink-0 text-slate-400" />
          <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search mail" className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-white" />
          {query ? <button type="button" onClick={() => { setQuery(""); void loadMessages(folder, "", 0); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"><X size={16} /></button> : null}
        </form>
      </div>

      <div className="relative flex h-11 shrink-0 items-center gap-2 border-y border-slate-200 bg-white px-3 dark:border-white/10 dark:bg-slate-900 sm:px-4">
        <label className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10" title="Select all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} className="h-4 w-4 accent-[#0b57d0]" /></label>
        {selectedUids.size ? (
          <div className="flex min-w-0 flex-1 items-center gap-1">
            <button type="button" onClick={() => void bulkMove(archiveFolder)} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Archive selected"><Archive size={16} /></button>
            <button type="button" onClick={() => void bulkDelete()} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600" title="Delete selected"><Trash2 size={16} /></button>
            <button type="button" onClick={() => void bulkFlags({ seen: false })} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Mark unread"><Mail size={16} /></button>
            <button type="button" onClick={() => void bulkFlags({ flagged: true })} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Star selected"><Star size={16} /></button>
            <span className="truncate text-[10px] font-bold text-slate-500">{selectedUids.size} selected</span>
          </div>
        ) : (
          <div className="min-w-0 flex-1"><p className="truncate text-xs font-black uppercase tracking-[.12em] text-slate-600 dark:text-slate-300">{inboxView === "primary" ? folder : inboxView}</p><p className="text-[10px] font-medium text-slate-400">{threadedView ? `${displayedThreads.length} conversation${displayedThreads.length === 1 ? "" : "s"} · ${visibleMessages.length} message${visibleMessages.length === 1 ? "" : "s"}` : `${visibleMessages.length} loaded message${visibleMessages.length === 1 ? "" : "s"}`}</p></div>
        )}
        <label className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-slate-500"><span className="hidden lg:inline">Sort</span><select aria-label="Sort loaded inbox messages" value={inboxSort} onChange={(event) => setInboxSort(event.target.value as InboxSort)} className="max-w-[112px] rounded-lg border border-slate-200 bg-white px-1.5 py-1.5 text-[11px] text-slate-700 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200"><option value="newest">Newest</option><option value="attention">Needs attention</option><option value="unread">Unread first</option><option value="starred">Starred first</option></select></label>
        <button type="button" onClick={() => setThreadedView((value) => !value)} className={`flex h-8 items-center gap-1.5 rounded-lg px-2 text-[10px] font-black uppercase tracking-[.05em] ${threadedView ? "bg-[#eaf1fb] text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200" : "text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"}`} title={threadedView ? "Show individual messages" : "Group related messages into conversations"}><Mail size={14} /><span className="hidden sm:inline">{threadedView ? "Threads" : "Messages"}</span></button>
        <button type="button" onClick={() => void refresh()} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button>
        <button type="button" onClick={() => setFilterOpen((value) => !value)} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="More"><MoreVertical size={16} /></button>
        <div className="hidden items-center gap-0.5 text-[10px] text-slate-500 xl:flex"><span className="mr-1">{pageStart}-{pageEnd} of {total}</span><button disabled={offset === 0 || loading} onClick={() => void loadMessages(folder, query, Math.max(0, offset - PAGE_SIZE))} className="grid h-8 w-8 place-items-center rounded-full hover:bg-slate-100 disabled:opacity-30"><ChevronLeft size={15} /></button><button disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void loadMessages(folder, query, offset + PAGE_SIZE)} className="grid h-8 w-8 place-items-center rounded-full hover:bg-slate-100 disabled:opacity-30"><ChevronRight size={15} /></button></div>
        {filterOpen ? <div className="absolute right-3 top-10 z-30 w-56 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-xl dark:border-white/10 dark:bg-slate-900"><label className="flex items-center justify-between gap-3 py-2"><span className="font-semibold text-slate-700 dark:text-slate-200">Unread only</span><input type="checkbox" checked={onlyUnread} onChange={(event) => setOnlyUnread(event.target.checked)} /></label><label className="flex items-center justify-between gap-3 py-2"><span className="font-semibold text-slate-700 dark:text-slate-200">Has attachment</span><input type="checkbox" checked={onlyAttachments} onChange={(event) => setOnlyAttachments(event.target.checked)} /></label><button type="button" onClick={() => { setOnlyUnread(false); setOnlyAttachments(false); setFilterOpen(false); }} className="mt-2 w-full rounded-lg bg-slate-100 px-3 py-2 font-bold text-slate-600 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200">Clear filters</button></div> : null}
      </div>

      {loading && !messages.length ? <div className="grid flex-1 place-items-center p-6"><MailLoading compact label="Loading mail" detail={`Reading ${folder}`} /></div> : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? <div className="m-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700"><span className="flex-1">{error}</span><button onClick={() => setError("")}><X size={14} /></button></div> : null}
          {!visibleMessages.length ? <div className="grid min-h-[360px] place-items-center p-8 text-center"><div><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm dark:bg-white/5"><Inbox size={24} /></span><p className="mt-4 text-sm font-black text-slate-700 dark:text-slate-200">No messages here</p><p className="mt-1 text-xs text-slate-500">{query ? "Try a different search." : "This mailbox view is currently empty."}</p></div></div> : displayedThreads.map((thread) => {
            const row = thread.latest;
            const threadSelected = thread.messages.every((item) => selectedUids.has(item.uid));
            const expanded = expandedThreads.has(thread.key);
            const unread = thread.unreadCount > 0;
            const senderSummary = thread.senderLabels.join(", ");
            return (
              <div key={`${folder}-${thread.key}`} className="border-b border-slate-200/80 dark:border-white/[.07]">
                <div className={`group flex cursor-pointer items-start gap-2 px-2 transition hover:z-[1] hover:bg-white hover:shadow-sm dark:hover:bg-white/[.045] ${unread ? "bg-white dark:bg-slate-900" : "bg-[#f7f9f8] dark:bg-[#0e1514]"} ${densityClass} ${thread.messages.some((item) => item.uid === selected?.uid) ? "border-l-[3px] border-l-[#0b57d0] bg-[#eef4ff] dark:bg-blue-400/[.06]" : "border-l-[3px] border-l-transparent"}`} onClick={() => void openMessage(row)}>
                  <label onClick={(event) => event.stopPropagation()} className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10" title={thread.messages.length > 1 ? "Select conversation" : "Select message"}><input type="checkbox" checked={threadSelected} onChange={() => toggleThreadSelection(thread)} className="h-4 w-4 accent-[#0b57d0]" /></label>
                  <button type="button" onClick={(event) => { event.stopPropagation(); void setThreadFlags(thread, { flagged: !thread.flagged }); }} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full transition hover:bg-slate-100 dark:hover:bg-white/10 ${thread.flagged ? "text-amber-500" : "text-slate-300 group-hover:text-slate-500"}`} title={thread.flagged ? "Unstar conversation" : "Star conversation"}><Star size={16} fill={thread.flagged ? "currentColor" : "none"} /></button>
                  <span className="hidden h-8 w-8 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-[10px] font-black text-[#174ea6] md:grid dark:bg-blue-400/10 dark:text-blue-200">{initials(row.from)}</span>
                  <div className="min-w-0 flex-1 sm:grid sm:grid-cols-[minmax(96px,150px)_1fr_auto] sm:items-center sm:gap-3">
                    <div className={`flex min-w-0 items-center gap-1.5 text-sm ${unread ? "font-black text-slate-950 dark:text-white" : "font-medium text-slate-700 dark:text-slate-300"}`}>
                      <span className="truncate">{senderSummary}</span>
                      {thread.messages.length > 1 ? <span className="shrink-0 rounded-full bg-slate-200/80 px-1.5 py-0.5 text-[9px] font-black text-slate-600 dark:bg-white/10 dark:text-slate-300">{thread.messages.length}</span> : null}
                    </div>
                    <div className="min-w-0"><div className={`flex min-w-0 items-center gap-2 truncate text-sm ${unread ? "font-bold text-slate-950 dark:text-white" : "font-medium text-slate-700 dark:text-slate-300"}`}><span className="truncate">{row.subject || "(no subject)"}</span>{thread.unreadCount > 0 && thread.messages.length > 1 ? <span className="shrink-0 text-[9px] font-black uppercase text-[#174ea6] dark:text-blue-200">{thread.unreadCount} unread</span> : null}</div>{preferences.showPreview ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{row.snippet}</p> : null}</div>
                    <div className="mt-1 flex items-center gap-2 sm:mt-0 sm:justify-end">{thread.attachmentCount ? <span className="flex items-center gap-1 text-[9px] font-bold text-slate-400"><Paperclip size={13} />{thread.attachmentCount > 1 ? thread.attachmentCount : ""}</span> : null}<time className={`text-[10px] ${unread ? "font-black text-[#174ea6] dark:text-blue-200" : "font-medium text-slate-400"}`}>{shortDate(row.date)}</time></div>
                  </div>
                  {thread.messages.length > 1 ? <button type="button" onClick={(event) => { event.stopPropagation(); toggleThreadExpanded(thread.key); }} className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10" title={expanded ? "Collapse conversation" : "Expand conversation"}><ChevronRight size={15} className={`transition ${expanded ? "rotate-90" : ""}`} /></button> : null}
                  <div className="hidden shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 xl:flex"><button type="button" onClick={(event) => { event.stopPropagation(); void Promise.all(thread.messages.map((item) => moveRow(item, archiveFolder))); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Archive conversation"><Archive size={15} /></button><button type="button" onClick={(event) => { event.stopPropagation(); void Promise.all(thread.messages.map((item) => deleteRow(item))); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600" title="Delete conversation"><Trash2 size={15} /></button><button type="button" onClick={(event) => { event.stopPropagation(); void setThreadFlags(thread, { seen: unread }); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title={unread ? "Mark conversation read" : "Mark conversation unread"}><Mail size={15} /></button></div>
                </div>
                {expanded ? (
                  <div className="bg-slate-50/70 pl-16 pr-3 dark:bg-white/[.02] sm:pl-24">
                    {thread.messages.map((item, index) => (
                      <button key={`${thread.key}-${item.uid}`} type="button" onClick={() => void openMessage(item)} className={`flex w-full items-start gap-3 border-t border-slate-200/70 py-2.5 text-left transition hover:bg-white/70 dark:border-white/[.06] dark:hover:bg-white/[.03] ${selected?.uid === item.uid ? "text-[#174ea6] dark:text-blue-200" : ""}`}>
                        <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white text-[9px] font-black text-slate-500 shadow-sm dark:bg-white/10 dark:text-slate-300">{initials(item.from)}</span>
                        <span className="min-w-0 flex-1"><span className={`block truncate text-xs ${item.seen ? "font-semibold text-slate-600 dark:text-slate-300" : "font-black text-slate-900 dark:text-white"}`}>{senderName(item.from)}{index === 0 ? " · latest" : ""}</span><span className="mt-0.5 block truncate text-[10px] text-slate-500">{item.snippet || item.subject}</span></span>
                        {item.attachments?.length ? <Paperclip size={12} className="mt-1 shrink-0 text-slate-400" /> : null}
                        <time className="mt-0.5 shrink-0 text-[9px] font-medium text-slate-400">{shortDate(item.date)}</time>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );

  return (
    <main className={`imail-hosted-workspace min-h-screen ${theme === "dark" ? "bg-[#0b1110] text-slate-100" : theme === "ithute" ? "bg-[#eef4f1] text-slate-900" : "bg-[#f4f6f8] text-slate-900"}`}>
      <header className="sticky top-0 z-40 flex h-16 items-center gap-2 border-b border-slate-200 bg-white/95 px-2 backdrop-blur dark:border-white/10 dark:bg-slate-950/95 sm:px-4">
        <button className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10 lg:hidden" onClick={() => setMobileFolders(true)} aria-label="Open folders"><Menu size={20} /></button>
        <div className="grid h-10 w-10 place-items-center rounded-[14px] bg-gradient-to-br from-emerald-950 to-emerald-700 text-xs font-black text-amber-300 shadow-sm">iM</div>
        <div className="min-w-0"><p className="truncate text-sm font-black text-slate-950 dark:text-white">{displayName || address}</p><p className="truncate text-[10px] font-semibold text-slate-500">Ithute hosted mailbox</p></div>
        <span className="ml-2 hidden rounded-full border border-blue-900/10 bg-[#eaf1fb] px-2.5 py-1 text-[10px] font-black uppercase tracking-[.1em] text-[#174ea6] sm:inline-flex">iMail</span>
        <div className="ml-auto flex items-center gap-0.5">
          <button type="button" onClick={() => void refresh()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={17} className={loading ? "animate-spin" : ""} /></button>
          <button type="button" onClick={() => setSettingsOpen(true)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Settings"><Settings2 size={17} /></button>
          <button type="button" onClick={() => void logout()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Sign out"><LogOut size={17} /></button>
        </div>
      </header>

      <div className="flex h-[calc(100vh-4rem)] min-h-0">
        <aside className={`${mobileFolders ? "fixed inset-0 z-50 flex" : "hidden"} w-full bg-black/30 lg:static lg:flex lg:w-[244px] lg:shrink-0 lg:bg-transparent`}>
          <button aria-label="Close folders" className="absolute inset-0 lg:hidden" onClick={() => setMobileFolders(false)} />
          <div className="relative flex h-full w-[84%] max-w-[286px] flex-col border-r border-slate-200 bg-[#f8fafd] p-2.5 dark:border-white/10 dark:bg-[#0e1514] lg:w-[244px] lg:max-w-none">
            <div className="mb-1 flex items-center justify-between px-2 lg:hidden"><span className="text-sm font-black">Folders</span><button type="button" onClick={() => setMobileFolders(false)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100"><X size={18} /></button></div>
            <button type="button" onClick={() => { startNew(); setMobileFolders(false); }} className="mb-3 flex h-12 w-full items-center gap-3 rounded-2xl bg-[#eaf1fb] px-4 text-sm font-black text-[#174ea6] shadow-sm transition hover:bg-[#dce8fb]" title="Compose"><PenLine size={18} /> Compose</button>
            <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto">
              <button type="button" onClick={() => openVirtualView("starred")} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${inboxView === "starred" ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title="Starred"><Star size={17} /><span className="min-w-0 flex-1 truncate">Starred</span></button>
              <button type="button" onClick={() => openVirtualView("attachments")} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${inboxView === "attachments" ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title="Attachments"><Paperclip size={17} /><span className="min-w-0 flex-1 truncate">Attachments</span></button>
              {folders.map((item) => {
                const active = folder === item.name && inboxView === "primary";
                const count = countFor(item.name);
                return <button key={item.name} type="button" onClick={() => openFolder(item.name)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${active ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title={item.name}>{folderIcon(item.name)}<span className="min-w-0 flex-1 truncate">{item.name}</span>{count ? <span className={`text-[10px] ${active ? "font-black text-[#174ea6]" : "font-bold text-slate-400"}`}>{count}</span> : null}</button>;
              })}

              {businessContacts.length ? <div className="mt-4 border-t border-slate-200 pt-3 dark:border-white/10">
                <div className="mb-1 flex items-center justify-between px-2">
                  <span className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[.12em] text-slate-500"><UsersRound size={13}/> Business contacts</span>
                  <span className="text-[9px] font-bold text-slate-400">{businessContacts.filter((item) => item.online).length} online</span>
                </div>
                <div className="space-y-2">
                  {contactGroups.map(([domain, group]) => <div key={domain}>
                    <div className="flex items-center gap-1 px-2 py-1 text-[9px] font-black uppercase tracking-[.1em] text-slate-400"><Building2 size={10}/><span className="truncate">{domain}</span></div>
                    <div className="space-y-0.5">
                      {group.map((contact) => {
                        const active = activeBusinessContact === contact.email;
                        const title = contact.name || senderName(contact.email);
                        return <button key={contact.email} type="button" onClick={() => void openBusinessContact(contact)} className={`flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left transition ${active ? "bg-[#eaf1fb] text-[#174ea6]" : "hover:bg-slate-100 dark:hover:bg-white/5"}`} title={`${contact.email} · ${contact.interactions || 0} interactions`}>
                          <span className="relative grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white text-[10px] font-black text-slate-600 shadow-sm ring-1 ring-slate-200 dark:bg-white/10 dark:text-slate-100 dark:ring-white/10">
                            {initials(title)}
                            <span className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#f8fafd] dark:border-[#0e1514] ${contact.online ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}`} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-1 truncate text-[11px] font-black text-slate-700 dark:text-slate-100">{contact.pinned ? <Star size={9} fill="currentColor" className="shrink-0 text-amber-500"/> : null}<span className="truncate">{title}</span></span>
                            <span className="block truncate text-[9px] font-medium text-slate-400">{contact.online ? "Online now" : `${contact.interactions || 0} interactions`}</span>
                          </span>
                        </button>;
                      })}
                    </div>
                  </div>)}
                </div>
              </div> : null}
            </nav>
            <div className="mt-2 rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-white/[.035]"><p className="truncate text-xs font-black text-slate-800 dark:text-white">{displayName || address}</p>{displayName ? <p className="mt-0.5 truncate text-[10px] font-medium text-slate-500">{address}</p> : null}<Link href="/webmail/settings" className="mt-2 inline-flex text-[10px] font-black text-[#174ea6] hover:underline">Full mailbox settings</Link></div>
          </div>
        </aside>

        <div className="min-w-0 flex-1 overflow-hidden">
          {noPane ? (
            <div className="flex h-full min-h-0">{selected ? reader : relationshipWorkspace || messageList}</div>
          ) : (
            <>
              <div className={`hidden h-full min-h-0 lg:grid ${paneRight ? "grid-cols-[minmax(390px,46%)_1fr]" : paneBottom ? "grid-rows-[minmax(300px,48%)_1fr]" : "grid-cols-[minmax(390px,46%)_1fr]"}`}>{messageList}{selected ? reader : relationshipWorkspace || reader}</div>
              <div className="flex h-full min-h-0 lg:hidden">{selected ? reader : relationshipWorkspace || messageList}</div>
            </>
          )}
        </div>
      </div>

      {composeOpen ? <MailCompose address={address} compose={compose} setCompose={setCompose} loading={loading} minimized={composeMinimized} expanded={composeExpanded} showCcBcc={showCcBcc} signatureHtml={signatureHtml} onMinimized={setComposeMinimized} onExpanded={setComposeExpanded} onShowCcBcc={setShowCcBcc} onClose={() => setComposeOpen(false)} onDiscard={discardDraft} onSaveDraft={() => void saveDraft()} onSend={sendMessage} onAttach={(files) => void attachFiles(files)} /> : null}

      <MailSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} preferences={preferences} setPreferences={setPreferences} onReset={resetPreferences} displayName={displayNameDraft} signatureHtml={signatureDraft} onDisplayNameChange={setDisplayNameDraft} onSignatureChange={setSignatureDraft} onSaveAccount={() => void saveAccountSettings()} savingAccount={savingSettings} />

      {notice ? <div className="fixed bottom-5 left-1/2 z-[120] -translate-x-1/2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white shadow-xl sm:left-5 sm:translate-x-0">{notice}</div> : null}
    </main>
  );
}
