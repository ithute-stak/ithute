"use client";

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  CalendarClock,
  ChevronDown,
  Clock3,
  Eraser,
  FileText,
  Italic,
  Link2,
  List,
  ListOrdered,
  Maximize2,
  Minimize2,
  Paperclip,
  Quote,
  Redo2,
  Save,
  Send,
  Signature,
  Trash2,
  Underline,
  Undo2,
  X,
} from "lucide-react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ComposeState, Contact } from "./mail-types";
import { emptyCompose, stripHtml, textToHtml, webmail } from "./mail-types";

type SenderIdentity = {
  key: string;
  address: string;
  displayName: string;
  type: "hosted" | "connected";
  provider?: string;
  status?: string;
};

type ComposeTemplate = { id: string; name: string; subject: string; body_text: string; body_html: string };
type ComposeSignature = { id: string; name: string; html: string; is_default?: boolean };

type Props = {
  address: string;
  compose: ComposeState;
  setCompose: Dispatch<SetStateAction<ComposeState>>;
  loading: boolean;
  minimized: boolean;
  expanded: boolean;
  showCcBcc: boolean;
  signatureHtml: string;
  onMinimized: (value: boolean) => void;
  onExpanded: (value: boolean) => void;
  onShowCcBcc: (value: boolean) => void;
  onClose: () => void;
  onDiscard: () => void;
  onSaveDraft: () => void;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  onAttach: (files: FileList | null) => void;
};

type RecipientFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  trailing?: ReactNode;
};

function ToolButton({ title, children, onClick }: { title: string; children: ReactNode; onClick: () => void }) {
  return <button type="button" title={title} aria-label={title} onMouseDown={(event) => event.preventDefault()} onClick={onClick} className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-[#44546a] hover:bg-[#e8edf5] hover:text-[#1f2937]">{children}</button>;
}

function recipientAddress(value: string) {
  const trimmed = value.trim();
  const angle = trimmed.match(/<([^>]+)>/);
  return (angle?.[1] || trimmed).trim();
}

function recipientList(value: string) {
  return value.split(/[;,\n]/).map(recipientAddress).filter(Boolean);
}

function uniqueRecipients(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function serializeRecipients(tokens: string[], draft: string) {
  return [...tokens, ...(draft.trim() ? [draft.trim()] : [])].join(", ");
}

function RecipientField({ label, value, onChange, placeholder = "Add recipient", required = false, trailing }: RecipientFieldProps) {
  const [tokens, setTokens] = useState<string[]>(() => uniqueRecipients(recipientList(value)));
  const [draft, setDraft] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactOpen, setContactOpen] = useState(false);
  const emittedRef = useRef(value);

  useEffect(() => {
    if (value === emittedRef.current) return;
    emittedRef.current = value;
    setTokens(uniqueRecipients(recipientList(value)));
    setDraft("");
  }, [value]);

  useEffect(() => {
    const term = draft.trim();
    if (term.length < 2) { setContacts([]); setContactOpen(false); return; }
    const timer = window.setTimeout(() => {
      void webmail(`/contacts?q=${encodeURIComponent(term)}`)
        .then(async (response) => response.ok ? response.json() : { items: [] })
        .then((payload) => {
          const items = ((payload.items || []) as Contact[]).filter((contact) => !tokens.some((token) => token.toLowerCase() === contact.email.toLowerCase())).slice(0, 7);
          setContacts(items);
          setContactOpen(Boolean(items.length));
        }).catch(() => undefined);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [draft, tokens]);

  function emit(nextTokens: string[], nextDraft = "") {
    const next = serializeRecipients(nextTokens, nextDraft);
    emittedRef.current = next;
    onChange(next);
  }

  function add(values: string[]) {
    const clean = values.map(recipientAddress).filter(Boolean);
    if (!clean.length) return;
    const nextTokens = uniqueRecipients([...tokens, ...clean]);
    setTokens(nextTokens); setDraft(""); setContactOpen(false); emit(nextTokens);
  }

  function remove(index: number) {
    const nextTokens = tokens.filter((_, tokenIndex) => tokenIndex !== index);
    setTokens(nextTokens); emit(nextTokens, draft);
  }

  return <div className="relative flex min-h-11 items-start border-b border-[#e5e7eb] py-1.5">
    <span className="w-12 shrink-0 pt-1.5 text-xs font-semibold text-[#5b6575]">{label}</span>
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
      {tokens.map((token, index) => <span key={`${token}-${index}`} className="inline-flex max-w-full items-center gap-1 rounded-full border border-[#c9d6eb] bg-[#eef4ff] py-1 pl-2.5 pr-1 text-xs font-medium text-[#244a7c]"><span className="max-w-[220px] truncate">{token}</span><button type="button" onClick={() => remove(index)} className="grid h-5 w-5 place-items-center rounded-full hover:bg-[#dce8fb]" aria-label={`Remove ${token}`}><X size={12} /></button></span>)}
      <input value={draft} onChange={(event) => { setDraft(event.target.value); emit(tokens, event.target.value); }} onFocus={() => setContactOpen(Boolean(contacts.length))} onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === "Tab" || event.key === "," || event.key === ";") && draft.trim()) { event.preventDefault(); add(recipientList(draft)); }
        else if (event.key === "Backspace" && !draft && tokens.length) { const next = tokens.slice(0, -1); const last = tokens[tokens.length - 1]; setTokens(next); setDraft(last); emit(next, last); }
      }} onPaste={(event) => { const pasted = event.clipboardData.getData("text"); if (!/[;,\n]/.test(pasted)) return; event.preventDefault(); add(recipientList(pasted)); }} className="min-w-[150px] flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-[#8a94a3]" placeholder={tokens.length ? "" : placeholder} autoComplete="off" required={required && tokens.length === 0} aria-label={`${label} recipients`} />
    </div>
    {trailing ? <div className="ml-2 shrink-0 pt-1">{trailing}</div> : null}
    {contactOpen ? <div className="absolute left-12 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-[#cfd6df] bg-white py-1 shadow-[0_14px_36px_rgba(15,23,42,.16)]">{contacts.map((contact) => <button key={contact.email} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => add([contact.email])} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-[#f1f5fb]"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#dce8fb] text-xs font-bold text-[#315b8c]">{(contact.name || contact.email)[0]?.toUpperCase()}</span><span className="min-w-0"><span className="block truncate text-sm font-medium text-[#202124]">{contact.name || contact.email}</span><span className="block truncate text-xs text-[#6b7280]">{contact.email}</span></span></button>)}</div> : null}
  </div>;
}

function presetTime(kind: "later" | "tomorrow" | "monday") {
  const date = new Date();
  if (kind === "later") date.setHours(date.getHours() + 2, 0, 0, 0);
  if (kind === "tomorrow") { date.setDate(date.getDate() + 1); date.setHours(8, 0, 0, 0); }
  if (kind === "monday") {
    const day = date.getDay();
    const add = day === 0 ? 1 : 8 - day;
    date.setDate(date.getDate() + add); date.setHours(8, 0, 0, 0);
  }
  return date;
}

export function MailCompose({ address, compose, setCompose, loading, minimized, expanded, showCcBcc, signatureHtml, onMinimized, onExpanded, onShowCcBcc, onClose, onDiscard, onSaveDraft, onSend, onAttach }: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<Range | null>(null);
  const [formatOpen, setFormatOpen] = useState(true);
  const [sendMenuOpen, setSendMenuOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [senderKey, setSenderKey] = useState("hosted");
  const [senders, setSenders] = useState<SenderIdentity[]>([{ key: "hosted", address, displayName: "", type: "hosted" }]);
  const [templates, setTemplates] = useState<ComposeTemplate[]>([]);
  const [signatures, setSignatures] = useState<ComposeSignature[]>([]);
  const [signatureKey, setSignatureKey] = useState("legacy");
  const [followUpDays, setFollowUpDays] = useState(0);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [undoJob, setUndoJob] = useState<{ id: string; seconds: number } | null>(null);

  const sender = useMemo(() => senders.find((item) => item.key === senderKey) || senders[0], [senderKey, senders]);
  const selectedSignature = useMemo(() => signatureKey === "legacy" ? signatureHtml : signatures.find((item) => item.id === signatureKey)?.html || "", [signatureHtml, signatureKey, signatures]);

  useEffect(() => {
    if (!address) return;
    void Promise.all([webmail("/connected-accounts"), webmail("/compose-templates"), webmail("/compose-signatures")]).then(async ([accountsResponse, templateResponse, signatureResponse]) => {
      if (accountsResponse.ok) {
        const payload = await accountsResponse.json();
        const hosted = payload.hosted || { address, display_name: "" };
        setSenders([{ key: "hosted", address: hosted.address || address, displayName: hosted.display_name || "", type: "hosted" }, ...((payload.items || []) as Array<Record<string, string>>).map((item) => ({ key: String(item.id), address: String(item.address), displayName: String(item.display_name || ""), type: "connected" as const, provider: String(item.provider || ""), status: String(item.status || "") }))]);
      }
      if (templateResponse.ok) setTemplates((await templateResponse.json()).items || []);
      if (signatureResponse.ok) {
        const items = ((await signatureResponse.json()).items || []) as ComposeSignature[];
        setSignatures(items);
        const preferred = items.find((item) => item.is_default);
        if (preferred) setSignatureKey(preferred.id);
      }
    }).catch(() => undefined);
  }, [address]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || document.activeElement === editor) return;
    const desired = compose.bodyHtml || textToHtml(compose.bodyText);
    if (editor.innerHTML !== desired) editor.innerHTML = desired;
  }, [compose.bodyHtml, compose.bodyText]);

  useEffect(() => {
    if (!undoJob) return;
    const timer = window.setInterval(() => setUndoJob((current) => current ? current.seconds <= 1 ? null : { ...current, seconds: current.seconds - 1 } : null), 1000);
    const closeTimer = window.setTimeout(() => { setCompose({ ...emptyCompose, attachments: [] }); onClose(); }, Math.max(1000, undoJob.seconds * 1000));
    return () => { window.clearInterval(timer); window.clearTimeout(closeTimer); };
  }, [onClose, setCompose, undoJob?.id]);

  function syncEditor() {
    const html = editorRef.current?.innerHTML || "";
    setCompose((current) => ({ ...current, bodyHtml: html, bodyText: stripHtml(html) }));
  }

  function rememberSelection() {
    const editor = editorRef.current; const selection = window.getSelection();
    if (!editor || !selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (editor.contains(range.commonAncestorContainer)) selectionRef.current = range.cloneRange();
  }

  function exec(command: string, value?: string) {
    const editor = editorRef.current; const selection = window.getSelection(); editor?.focus();
    if (selection && selectionRef.current) { selection.removeAllRanges(); selection.addRange(selectionRef.current); }
    document.execCommand(command, false, value); rememberSelection(); syncEditor();
  }

  function finalBodies() {
    const bodyHtml = compose.bodyHtml || textToHtml(compose.bodyText);
    const html = selectedSignature ? `${bodyHtml}${bodyHtml ? "<br><br>" : ""}${selectedSignature}` : bodyHtml;
    return { body_html: html, body_text: stripHtml(html) };
  }

  function payload() {
    const bodies = finalBodies();
    return { to: recipientList(compose.to), cc: recipientList(compose.cc), bcc: recipientList(compose.bcc), subject: compose.subject, ...bodies, attachments: compose.attachments, in_reply_to: compose.in_reply_to, references: compose.references };
  }

  async function createFollowUp(scheduledMailId = "") {
    if (!followUpDays) return;
    const recipient = recipientList(compose.to)[0];
    if (!recipient) return;
    const remind = new Date(); remind.setDate(remind.getDate() + followUpDays);
    await webmail("/follow-ups", { method: "POST", body: JSON.stringify({ recipient, subject: compose.subject, remind_at: remind.toISOString(), source_key: sender?.key || "hosted", scheduled_mail_id: scheduledMailId }) });
  }

  async function scheduleMessage(date: Date, undoSeconds = 0) {
    setActionBusy(true); setActionError(""); setSendMenuOpen(false);
    try {
      const body = payload();
      const response = await webmail("/scheduled", { method: "POST", body: JSON.stringify({ connected_account_id: sender?.type === "connected" ? sender.key : null, to: body.to, cc: body.cc, bcc: body.bcc, subject: body.subject, body_text: body.body_text, body_html: body.body_html, attachments: body.attachments, scheduled_at: date.toISOString() }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to schedule message");
      const job = await response.json();
      await createFollowUp(String(job.id || ""));
      if (undoSeconds) setUndoJob({ id: String(job.id), seconds: undoSeconds });
      else { setCompose({ ...emptyCompose, attachments: [] }); onClose(); }
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Unable to schedule message"); }
    finally { setActionBusy(false); }
  }

  async function undoSend() {
    if (!undoJob) return;
    setActionBusy(true);
    try {
      const response = await webmail(`/scheduled/${undoJob.id}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to undo send");
      setUndoJob(null);
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Unable to undo send"); }
    finally { setActionBusy(false); }
  }

  async function sendConnectedNow() {
    if (!sender || sender.type !== "connected") return;
    setActionBusy(true); setActionError("");
    try {
      const response = await webmail(`/connected-accounts/${sender.key}/send`, { method: "POST", body: JSON.stringify(payload()) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to send message");
      await createFollowUp();
      setCompose({ ...emptyCompose, attachments: [] }); onClose();
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Unable to send message"); }
    finally { setActionBusy(false); }
  }

  async function saveTemplate() {
    const name = window.prompt("Template name"); if (!name?.trim()) return;
    const response = await webmail("/compose-templates", { method: "POST", body: JSON.stringify({ name: name.trim(), subject: compose.subject, body_text: compose.bodyText || stripHtml(compose.bodyHtml), body_html: compose.bodyHtml }) });
    if (response.ok) { const row = await response.json(); setTemplates((items) => [...items, row].sort((a, b) => a.name.localeCompare(b.name))); }
  }

  async function addSignature() {
    const name = window.prompt("Signature name"); if (!name?.trim()) return;
    const text = window.prompt("Signature text"); if (text === null) return;
    const response = await webmail("/compose-signatures", { method: "POST", body: JSON.stringify({ name: name.trim(), html: textToHtml(text), is_default: signatures.length === 0 }) });
    if (response.ok) { const row = await response.json(); setSignatures((items) => [...items, row]); setSignatureKey(row.id); }
  }

  function insertTemplate(template: ComposeTemplate) {
    setCompose((current) => ({ ...current, subject: template.subject || current.subject, bodyText: template.body_text || stripHtml(template.body_html || ""), bodyHtml: template.body_html || textToHtml(template.body_text || "") }));
    setToolsOpen(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const undoAt = new Date(Date.now() + 25_000);
    void scheduleMessage(undoAt, 20);
  }

  if (undoJob) return <div className={`fixed z-[90] ${expanded ? "inset-0 flex items-center justify-center bg-black/30 p-4" : "bottom-4 right-4"}`}><div className="w-[min(94vw,460px)] rounded-2xl border border-emerald-200 bg-white p-5 shadow-2xl"><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-emerald-100 text-emerald-700"><Send size={18} /></span><div className="min-w-0 flex-1"><p className="font-bold text-slate-900">Message queued</p><p className="mt-1 text-sm text-slate-500">Sending in about {undoJob.seconds} seconds. You can undo before it leaves the mailbox.</p></div></div><div className="mt-4 flex justify-end gap-2"><button type="button" disabled={actionBusy} onClick={() => void undoSend()} className="rounded-xl bg-[#174ea6] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"><Undo2 size={15} className="mr-1.5 inline" />Undo send</button></div>{actionError ? <p className="mt-3 text-xs font-semibold text-red-600">{actionError}</p> : null}</div></div>;

  const ccBccToggle = <button type="button" onClick={() => onShowCcBcc(!showCcBcc)} className="rounded-md px-2 py-1 text-xs font-semibold text-[#4f6076] hover:bg-[#edf2f8]">{showCcBcc ? "Hide Cc/Bcc" : "Cc Bcc"}</button>;

  return <div className={`fixed z-[80] ${expanded ? "inset-0 flex items-center justify-center bg-black/30 p-3 sm:p-6" : "bottom-0 right-0 sm:right-5"}`}>
    <form onSubmit={handleSubmit} className={`mail-compose-window flex overflow-hidden bg-white shadow-2xl ${expanded ? "h-[94vh] w-full max-w-6xl rounded-2xl" : minimized ? "h-11 w-[min(94vw,470px)] rounded-t-xl" : "h-[min(780px,calc(100vh-70px))] w-[min(100vw,780px)] rounded-t-xl"}`}>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-11 shrink-0 items-center border-b border-[#dfe4ea] bg-[#eef3f9] px-3 sm:px-4"><p className="min-w-0 flex-1 truncate text-[13px] font-semibold text-[#263548]">New Message</p><div className="flex items-center gap-0.5"><ToolButton title={minimized ? "Restore" : "Minimize"} onClick={() => onMinimized(!minimized)}>{minimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}</ToolButton><ToolButton title={expanded ? "Exit full screen" : "Full screen"} onClick={() => { onExpanded(!expanded); onMinimized(false); }}><Maximize2 size={14} /></ToolButton><ToolButton title="Save and close" onClick={onClose}><X size={16} /></ToolButton></div></div>
        {!minimized ? <>
          <div className="shrink-0 bg-white px-3 sm:px-4">
            <div className="flex min-h-11 items-center border-b border-[#e5e7eb]"><span className="w-12 shrink-0 text-xs font-semibold text-[#5b6575]">From</span><select value={senderKey} onChange={(event) => setSenderKey(event.target.value)} className="min-w-0 flex-1 bg-transparent py-2.5 text-sm font-medium text-slate-700 outline-none"><option value="hosted">{senders[0]?.displayName ? `${senders[0].displayName} <${senders[0].address}>` : senders[0]?.address || address}</option>{senders.slice(1).map((item) => <option key={item.key} value={item.key}>{item.displayName ? `${item.displayName} <${item.address}>` : item.address}{item.provider ? ` · ${item.provider}` : ""}</option>)}</select></div>
            <RecipientField label="To" value={compose.to} onChange={(value) => setCompose((current) => ({ ...current, to: value }))} placeholder="Type a name or email, then press Enter" required trailing={ccBccToggle} />
            {showCcBcc ? <><RecipientField label="Cc" value={compose.cc} onChange={(value) => setCompose((current) => ({ ...current, cc: value }))} /><RecipientField label="Bcc" value={compose.bcc} onChange={(value) => setCompose((current) => ({ ...current, bcc: value }))} /></> : null}
            <label className="flex min-h-11 items-center border-b border-[#e5e7eb]"><span className="w-12 shrink-0 text-xs font-semibold text-[#5b6575]">Subject</span><input value={compose.subject} onChange={(event) => setCompose((current) => ({ ...current, subject: event.target.value }))} className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none" placeholder="Subject" /></label>
          </div>
          {formatOpen ? <div className="shrink-0 border-b border-[#d9e0e8] bg-[#f8fafc] px-2 py-1.5"><div className="flex items-center gap-1 overflow-x-auto"><select aria-label="Font family" defaultValue="Arial" onChange={(event) => exec("fontName", event.target.value)} className="h-8 w-28 shrink-0 rounded border border-[#cbd5e1] bg-white px-2 text-xs"><option>Arial</option><option>Calibri</option><option>Georgia</option><option>Tahoma</option><option>Times New Roman</option><option>Verdana</option></select><ToolButton title="Bold" onClick={() => exec("bold")}><Bold size={15} /></ToolButton><ToolButton title="Italic" onClick={() => exec("italic")}><Italic size={15} /></ToolButton><ToolButton title="Underline" onClick={() => exec("underline")}><Underline size={15} /></ToolButton><ToolButton title="Clear formatting" onClick={() => exec("removeFormat")}><Eraser size={15} /></ToolButton><ToolButton title="Align left" onClick={() => exec("justifyLeft")}><AlignLeft size={15} /></ToolButton><ToolButton title="Align center" onClick={() => exec("justifyCenter")}><AlignCenter size={15} /></ToolButton><ToolButton title="Align right" onClick={() => exec("justifyRight")}><AlignRight size={15} /></ToolButton><ToolButton title="Bulleted list" onClick={() => exec("insertUnorderedList")}><List size={15} /></ToolButton><ToolButton title="Numbered list" onClick={() => exec("insertOrderedList")}><ListOrdered size={15} /></ToolButton><ToolButton title="Quote" onClick={() => exec("formatBlock", "blockquote")}><Quote size={15} /></ToolButton><ToolButton title="Insert link" onClick={() => { const url = window.prompt("Paste a link"); if (url) exec("createLink", url); }}><Link2 size={15} /></ToolButton><ToolButton title="Undo" onClick={() => exec("undo")}><Undo2 size={15} /></ToolButton><ToolButton title="Redo" onClick={() => exec("redo")}><Redo2 size={15} /></ToolButton></div></div> : null}
          <div className="relative min-h-0 flex-1 overflow-y-auto bg-[#eef1f5] p-2.5 sm:p-4"><div className="mx-auto min-h-full max-w-[860px] border border-[#dde2e8] bg-white shadow-[0_2px_10px_rgba(15,23,42,.08)]"><div ref={editorRef} contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Message body" onInput={() => { syncEditor(); rememberSelection(); }} onMouseUp={rememberSelection} onKeyUp={rememberSelection} onFocus={rememberSelection} data-placeholder="Write your message" className="mail-rich-editor min-h-[330px] px-5 py-5 text-sm leading-6 text-[#202124] outline-none sm:px-7 sm:py-6" />{selectedSignature ? <div className="mx-5 mb-6 border-t border-transparent pt-2 text-sm text-[#5f6368] sm:mx-7" dangerouslySetInnerHTML={{ __html: selectedSignature }} /> : null}</div></div>
          {compose.attachments.length ? <div className="flex max-h-24 shrink-0 flex-wrap gap-2 overflow-y-auto border-t border-[#dfe4ea] bg-white px-4 py-2">{compose.attachments.map((attachment, index) => <button type="button" key={`${attachment.filename}-${index}`} onClick={() => setCompose((current) => ({ ...current, attachments: current.attachments.filter((_, itemIndex) => itemIndex !== index) }))} className="flex max-w-[260px] items-center gap-2 rounded-lg border border-[#cfd6df] bg-[#f8fafc] px-2.5 py-1.5 text-xs font-medium" title="Remove attachment"><Paperclip size={12} /><span className="truncate">{attachment.filename}</span><X size={12} /></button>)}</div> : null}
          <div className="relative shrink-0 border-t border-[#d9e0e8] bg-white px-2 py-2 sm:px-3">
            {actionError ? <div className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{actionError}</div> : null}
            <div className="flex items-center gap-1">
              <div className="relative flex overflow-visible rounded-md bg-[#2f5597] text-white shadow-sm">
                <button disabled={loading || actionBusy} type="submit" className="flex min-h-9 items-center gap-2 rounded-l-md px-5 text-sm font-semibold hover:bg-[#244779] disabled:opacity-60"><Send size={15} />{actionBusy ? "Working…" : "Send"}</button>
                <button type="button" onClick={() => setSendMenuOpen((value) => !value)} className="grid w-8 place-items-center rounded-r-md border-l border-white/25 hover:bg-[#244779]" title="Send options"><ChevronDown size={14} /></button>
                {sendMenuOpen ? <div className="absolute bottom-11 left-0 z-[100] w-72 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 text-left text-slate-700 shadow-2xl">
                  <button type="button" onClick={(event) => { setSendMenuOpen(false); if (sender?.type === "connected") void sendConnectedNow(); else onSend(event as unknown as FormEvent<HTMLFormElement>); }} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm font-semibold hover:bg-slate-50"><Send size={15} />Send immediately</button>
                  <button type="button" onClick={() => void scheduleMessage(presetTime("later"))} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-slate-50"><Clock3 size={15} />Later today</button>
                  <button type="button" onClick={() => void scheduleMessage(presetTime("tomorrow"))} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-slate-50"><CalendarClock size={15} />Tomorrow morning</button>
                  <button type="button" onClick={() => void scheduleMessage(presetTime("monday"))} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-slate-50"><CalendarClock size={15} />Monday morning</button>
                  <button type="button" onClick={() => { const value = window.prompt("Schedule date/time (example: 2026-09-10 14:30)"); if (!value) return; const date = new Date(value.replace(" ", "T")); if (!Number.isNaN(date.getTime())) void scheduleMessage(date); else setActionError("Invalid schedule date/time"); }} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-slate-50"><CalendarClock size={15} />Pick date & time…</button>
                  <div className="border-t border-slate-100 px-3 py-2 text-[10px] font-medium text-slate-400">Normal Send uses a short server-side delay so Undo Send remains reliable even if the browser refreshes.</div>
                </div> : null}
              </div>
              <button type="button" onClick={() => setFormatOpen((value) => !value)} className={`grid h-9 w-9 place-items-center rounded-md hover:bg-[#edf2f8] ${formatOpen ? "bg-[#e8eef8] text-[#2f5597]" : "text-[#5f6368]"}`} title="Formatting"><span className="text-[15px] font-semibold underline">A</span></button>
              <label className="grid h-9 w-9 cursor-pointer place-items-center rounded-md text-[#5f6368] hover:bg-[#edf2f8]" title="Attach files"><Paperclip size={17} /><input type="file" multiple className="hidden" onChange={(event) => onAttach(event.target.files)} /></label>
              <div className="relative"><button type="button" onClick={() => setToolsOpen((value) => !value)} className="grid h-9 w-9 place-items-center rounded-md text-[#5f6368] hover:bg-[#edf2f8]" title="Templates and signatures"><FileText size={17} /></button>{toolsOpen ? <div className="absolute bottom-11 left-0 z-[100] w-80 max-h-[360px] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-2xl"><p className="px-2 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400">Templates</p>{templates.map((item) => <button type="button" key={item.id} onClick={() => insertTemplate(item)} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"><FileText size={14} />{item.name}</button>)}<button type="button" onClick={() => void saveTemplate()} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-[#174ea6] hover:bg-blue-50"><Save size={14} />Save current message as template</button><div className="my-2 border-t border-slate-100" /><p className="px-2 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400">Signature</p><select value={signatureKey} onChange={(event) => setSignatureKey(event.target.value)} className="mb-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"><option value="legacy">Mailbox default</option><option value="none">No signature</option>{signatures.map((item) => <option key={item.id} value={item.id}>{item.name}{item.is_default ? " · default" : ""}</option>)}</select><button type="button" onClick={() => void addSignature()} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-[#174ea6] hover:bg-blue-50"><Signature size={14} />Add signature</button></div> : null}</div>
              <select value={followUpDays} onChange={(event) => setFollowUpDays(Number(event.target.value))} title="Follow-up reminder" className="hidden h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-600 md:block"><option value={0}>No follow-up</option><option value={1}>Follow up: 1 day</option><option value={3}>Follow up: 3 days</option><option value={7}>Follow up: 7 days</option></select>
              <button type="button" onClick={onSaveDraft} className="hidden rounded-md px-3 py-2 text-xs font-medium text-[#5f6368] hover:bg-[#edf2f8] sm:block">Save draft</button>
              <span className="ml-1 hidden max-w-[190px] truncate text-[10px] text-[#80868b] xl:block">From {sender?.address || address}</span>
              <button type="button" onClick={onDiscard} className="ml-auto grid h-9 w-9 place-items-center rounded-md text-[#5f6368] hover:bg-[#edf2f8]" title="Discard"><Trash2 size={16} /></button>
            </div>
          </div>
        </> : null}
      </div>
    </form>
  </div>;
}
