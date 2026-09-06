"use client";

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Eraser,
  Italic,
  Link2,
  List,
  ListOrdered,
  Maximize2,
  Minimize2,
  Paperclip,
  Quote,
  Redo2,
  Send,
  Trash2,
  Underline,
  Undo2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import type { ComposeState, Contact } from "./mail-types";
import { stripHtml, textToHtml } from "./mail-types";

type Props = {
  address: string;
  compose: ComposeState;
  setCompose: React.Dispatch<React.SetStateAction<ComposeState>>;
  loading: boolean;
  minimized: boolean;
  expanded: boolean;
  showCcBcc: boolean;
  title?: string;
  signatureHtml?: string;
  onMinimized: (value: boolean) => void;
  onExpanded: (value: boolean) => void;
  onShowCcBcc: (value: boolean) => void;
  onClose: () => void;
  onDiscard: () => void;
  onSaveDraft: () => void;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  onAttach: (files: FileList | null) => void;
  searchContacts: (query: string) => Promise<Contact[]>;
};

type RecipientFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  searchContacts: (query: string) => Promise<Contact[]>;
  placeholder?: string;
  required?: boolean;
  trailing?: React.ReactNode;
};

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

function ToolButton({ title, children, onClick }: { title: string; children: React.ReactNode; onClick: () => void }) {
  return <button type="button" title={title} aria-label={title} onMouseDown={(event) => event.preventDefault()} onClick={onClick} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white">{children}</button>;
}

function RecipientField({ label, value, onChange, searchContacts, placeholder = "Add recipient", required = false, trailing }: RecipientFieldProps) {
  const [tokens, setTokens] = useState<string[]>(() => uniqueRecipients(recipientList(value)));
  const [draft, setDraft] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [open, setOpen] = useState(false);
  const emittedRef = useRef(value);

  useEffect(() => {
    if (value === emittedRef.current) return;
    emittedRef.current = value;
    setTokens(uniqueRecipients(recipientList(value)));
    setDraft("");
  }, [value]);

  useEffect(() => {
    const term = draft.trim();
    if (term.length < 2) {
      setContacts([]);
      setOpen(false);
      return;
    }
    const timer = window.setTimeout(() => {
      void searchContacts(term).then((items) => {
        const filtered = items.filter((contact) => !tokens.some((token) => token.toLowerCase() === contact.email.toLowerCase())).slice(0, 7);
        setContacts(filtered);
        setOpen(Boolean(filtered.length));
      }).catch(() => undefined);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [draft, searchContacts, tokens]);

  function emit(nextTokens: string[], nextDraft = "") {
    const next = [...nextTokens, ...(nextDraft.trim() ? [nextDraft.trim()] : [])].join(", ");
    emittedRef.current = next;
    onChange(next);
  }

  function add(values: string[]) {
    const next = uniqueRecipients([...tokens, ...values.map(recipientAddress).filter(Boolean)]);
    setTokens(next);
    setDraft("");
    setOpen(false);
    emit(next);
  }

  return (
    <div className="relative flex min-h-11 items-start border-b border-slate-200 py-1.5 dark:border-white/10">
      <span className="w-12 shrink-0 pt-1.5 text-xs font-bold text-slate-500 dark:text-slate-400">{label}</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {tokens.map((token, index) => (
          <span key={`${token}-${index}`} className="inline-flex max-w-full items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 py-1 pl-2.5 pr-1 text-xs font-semibold text-emerald-900 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-100">
            <span className="max-w-[240px] truncate">{token}</span>
            <button type="button" onClick={() => { const next = tokens.filter((_, i) => i !== index); setTokens(next); emit(next, draft); }} className="grid h-5 w-5 place-items-center rounded-full hover:bg-emerald-100 dark:hover:bg-white/10" aria-label={`Remove ${token}`}><X size={12} /></button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => { setDraft(event.target.value); emit(tokens, event.target.value); }}
          onFocus={() => setOpen(Boolean(contacts.length))}
          onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === "Tab" || event.key === "," || event.key === ";") && draft.trim()) {
              event.preventDefault();
              add(recipientList(draft));
            } else if (event.key === "Backspace" && !draft && tokens.length) {
              const next = tokens.slice(0, -1);
              const last = tokens[tokens.length - 1];
              setTokens(next); setDraft(last); emit(next, last);
            }
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData.getData("text");
            if (!/[;,\n]/.test(pasted)) return;
            event.preventDefault(); add(recipientList(pasted));
          }}
          className="min-w-[150px] flex-1 bg-transparent py-1.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-white"
          placeholder={tokens.length ? "" : placeholder}
          required={required && tokens.length === 0}
          autoComplete="off"
        />
      </div>
      {trailing ? <div className="ml-2 shrink-0 pt-1">{trailing}</div> : null}
      {open ? <div className="absolute left-12 right-0 top-full z-30 mt-1 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-2xl dark:border-white/10 dark:bg-slate-900">
        {contacts.map((contact) => <button key={contact.email} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => add([contact.email])} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-white/5">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-emerald-100 text-xs font-black text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-200">{(contact.name || contact.email)[0]?.toUpperCase()}</span>
          <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{contact.name || contact.email}</span><span className="block truncate text-xs text-slate-500">{contact.email}</span></span>
        </button>)}
      </div> : null}
    </div>
  );
}

export function ExternalMailCompose({
  address, compose, setCompose, loading, minimized, expanded, showCcBcc, title = "New message", signatureHtml = "",
  onMinimized, onExpanded, onShowCcBcc, onClose, onDiscard, onSaveDraft, onSend, onAttach, searchContacts,
}: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<Range | null>(null);
  const [ribbonOpen, setRibbonOpen] = useState(true);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || document.activeElement === editor) return;
    const desired = compose.bodyHtml || textToHtml(compose.bodyText);
    if (editor.innerHTML !== desired) editor.innerHTML = desired;
  }, [compose.bodyHtml, compose.bodyText]);

  useEffect(() => {
    if (!signatureHtml || compose.bodyText.trim() || compose.bodyHtml.trim()) return;
    const clean = stripHtml(signatureHtml);
    setCompose((current) => ({ ...current, bodyText: `\n\n${clean}`, bodyHtml: `<br><br>${signatureHtml}` }));
  }, [compose.bodyHtml, compose.bodyText, setCompose, signatureHtml]);

  function syncEditor() {
    const html = editorRef.current?.innerHTML || "";
    setCompose((current) => ({ ...current, bodyHtml: html, bodyText: stripHtml(html) }));
  }

  function rememberSelection() {
    const editor = editorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (editor.contains(range.commonAncestorContainer)) selectionRef.current = range.cloneRange();
  }

  function exec(command: string, value?: string) {
    const selection = window.getSelection();
    editorRef.current?.focus();
    if (selection && selectionRef.current) { selection.removeAllRanges(); selection.addRange(selectionRef.current); }
    document.execCommand(command, false, value);
    rememberSelection(); syncEditor();
  }

  function addLink() {
    const url = window.prompt("Paste a secure link (https://…)");
    if (!url) return;
    const value = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    exec("createLink", value);
  }

  const ccBcc = <button type="button" onClick={() => onShowCcBcc(!showCcBcc)} className="rounded-lg px-2 py-1 text-xs font-bold text-slate-500 transition hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10">{showCcBcc ? "Hide Cc/Bcc" : "Cc Bcc"}</button>;

  return (
    <div className={`fixed z-[100] ${expanded ? "inset-0 flex items-center justify-center bg-slate-950/35 p-2 sm:p-5" : "bottom-0 right-0 sm:right-5"}`}>
      <form onSubmit={onSend} className={`flex overflow-hidden border border-slate-200 bg-white shadow-[0_28px_90px_rgba(15,23,42,.28)] dark:border-white/10 dark:bg-slate-900 ${expanded ? "h-[95vh] w-full max-w-6xl rounded-2xl" : minimized ? "h-12 w-[min(94vw,500px)] rounded-t-2xl" : "h-[min(790px,calc(100vh-68px))] w-[min(100vw,800px)] rounded-t-2xl"}`}>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 bg-gradient-to-r from-emerald-950 to-emerald-900 px-3 text-white dark:border-white/10 sm:px-4">
            <span className="min-w-0 flex-1 truncate text-[13px] font-bold">{title}</span>
            <span className="hidden rounded-full bg-white/10 px-2 py-1 text-[10px] font-semibold text-emerald-50 sm:block">From {address}</span>
            <ToolButton title={minimized ? "Restore" : "Minimize"} onClick={() => onMinimized(!minimized)}>{minimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}</ToolButton>
            <ToolButton title={expanded ? "Exit full screen" : "Full screen"} onClick={() => { onExpanded(!expanded); onMinimized(false); }}><Maximize2 size={14} /></ToolButton>
            <ToolButton title="Save and close" onClick={onClose}><X size={16} /></ToolButton>
          </div>

          {!minimized ? <>
            <div className="shrink-0 px-3 sm:px-4">
              <RecipientField label="To" value={compose.to} onChange={(value) => setCompose((current) => ({ ...current, to: value }))} searchContacts={searchContacts} required placeholder="Type an email and press Enter" trailing={ccBcc} />
              {showCcBcc ? <><RecipientField label="Cc" value={compose.cc} onChange={(value) => setCompose((current) => ({ ...current, cc: value }))} searchContacts={searchContacts} /><RecipientField label="Bcc" value={compose.bcc} onChange={(value) => setCompose((current) => ({ ...current, bcc: value }))} searchContacts={searchContacts} /></> : null}
              <label className="flex min-h-11 items-center border-b border-slate-200 dark:border-white/10"><span className="w-12 shrink-0 text-xs font-bold text-slate-500 dark:text-slate-400">Subject</span><input value={compose.subject} onChange={(event) => setCompose((current) => ({ ...current, subject: event.target.value }))} className="min-w-0 flex-1 bg-transparent py-2.5 text-sm text-slate-900 outline-none dark:text-white" placeholder="Subject" /></label>
            </div>

            {ribbonOpen ? <div className="shrink-0 border-b border-slate-200 bg-slate-50/80 dark:border-white/10 dark:bg-white/[.025]">
              <div className="flex h-8 items-end gap-4 border-b border-slate-200 px-3 text-xs font-bold text-slate-500 dark:border-white/10 dark:text-slate-400"><span className="border-b-2 border-emerald-700 px-1 pb-1 text-emerald-800 dark:border-emerald-400 dark:text-emerald-300">Home</span><span className="pb-1">Message</span></div>
              <div className="flex min-h-12 items-center gap-1 overflow-x-auto px-2 py-1.5 sm:px-3">
                <select aria-label="Font family" defaultValue="Arial" onChange={(event) => exec("fontName", event.target.value)} className="h-8 w-28 shrink-0 rounded-lg border border-slate-200 bg-white px-2 text-xs dark:border-white/10 dark:bg-slate-800"><option>Arial</option><option>Calibri</option><option>Georgia</option><option>Tahoma</option><option>Times New Roman</option><option>Verdana</option></select>
                <select aria-label="Font size" defaultValue="3" onChange={(event) => exec("fontSize", event.target.value)} className="h-8 w-16 shrink-0 rounded-lg border border-slate-200 bg-white px-1.5 text-xs dark:border-white/10 dark:bg-slate-800"><option value="2">10</option><option value="3">12</option><option value="4">14</option><option value="5">18</option><option value="6">24</option><option value="7">32</option></select>
                <span className="mx-1 h-7 w-px bg-slate-200 dark:bg-white/10" />
                <ToolButton title="Bold" onClick={() => exec("bold")}><Bold size={16} /></ToolButton><ToolButton title="Italic" onClick={() => exec("italic")}><Italic size={16} /></ToolButton><ToolButton title="Underline" onClick={() => exec("underline")}><Underline size={16} /></ToolButton>
                <span className="mx-1 h-7 w-px bg-slate-200 dark:bg-white/10" />
                <ToolButton title="Bullets" onClick={() => exec("insertUnorderedList")}><List size={16} /></ToolButton><ToolButton title="Numbered list" onClick={() => exec("insertOrderedList")}><ListOrdered size={16} /></ToolButton><ToolButton title="Quote" onClick={() => exec("formatBlock", "blockquote")}><Quote size={16} /></ToolButton>
                <span className="mx-1 h-7 w-px bg-slate-200 dark:bg-white/10" />
                <ToolButton title="Align left" onClick={() => exec("justifyLeft")}><AlignLeft size={16} /></ToolButton><ToolButton title="Center" onClick={() => exec("justifyCenter")}><AlignCenter size={16} /></ToolButton><ToolButton title="Align right" onClick={() => exec("justifyRight")}><AlignRight size={16} /></ToolButton>
                <span className="mx-1 h-7 w-px bg-slate-200 dark:bg-white/10" />
                <ToolButton title="Add link" onClick={addLink}><Link2 size={16} /></ToolButton><ToolButton title="Undo" onClick={() => exec("undo")}><Undo2 size={16} /></ToolButton><ToolButton title="Redo" onClick={() => exec("redo")}><Redo2 size={16} /></ToolButton><ToolButton title="Clear formatting" onClick={() => exec("removeFormat")}><Eraser size={16} /></ToolButton>
              </div>
            </div> : null}

            <div className="min-h-0 flex-1 overflow-y-auto bg-white dark:bg-slate-900">
              <div ref={editorRef} contentEditable suppressContentEditableWarning onInput={syncEditor} onBlur={syncEditor} onKeyUp={rememberSelection} onMouseUp={rememberSelection} className="min-h-full px-5 py-5 text-[14px] leading-7 text-slate-900 outline-none dark:text-slate-100 sm:px-7" data-placeholder="Write your message…" />
            </div>

            {compose.attachments.length ? <div className="flex shrink-0 flex-wrap gap-2 border-t border-slate-200 px-4 py-2.5 dark:border-white/10">{compose.attachments.map((item, index) => <span key={`${item.filename}-${index}`} className="inline-flex max-w-[260px] items-center gap-2 rounded-full border border-slate-200 bg-slate-50 py-1.5 pl-3 pr-1.5 text-xs font-semibold dark:border-white/10 dark:bg-white/5"><Paperclip size={13} /><span className="truncate">{item.filename}</span><button type="button" onClick={() => setCompose((current) => ({ ...current, attachments: current.attachments.filter((_, i) => i !== index) }))} className="grid h-5 w-5 place-items-center rounded-full hover:bg-slate-200 dark:hover:bg-white/10"><X size={12} /></button></span>)}</div> : null}

            <div className="flex min-h-14 shrink-0 items-center gap-2 border-t border-slate-200 px-3 py-2 dark:border-white/10 sm:px-4">
              <button disabled={loading} type="submit" className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-5 text-sm font-black text-white shadow-sm transition hover:bg-emerald-900 disabled:opacity-60"><Send size={16} /> {loading ? "Sending…" : "Send"}</button>
              <label className="grid h-9 w-9 cursor-pointer place-items-center rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10" title="Attach files"><Paperclip size={18} /><input type="file" multiple className="hidden" onChange={(event) => { void onAttach(event.target.files); event.currentTarget.value = ""; }} /></label>
              <button type="button" onClick={() => setRibbonOpen((value) => !value)} className="h-9 rounded-lg px-3 text-xs font-bold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10">{ribbonOpen ? "Hide formatting" : "Formatting"}</button>
              <button type="button" disabled={loading} onClick={onSaveDraft} className="ml-auto h-9 rounded-lg px-3 text-xs font-bold text-slate-500 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-400 dark:hover:bg-white/10">Save draft</button>
              <ToolButton title="Discard" onClick={onDiscard}><Trash2 size={17} /></ToolButton>
            </div>
          </> : null}
        </div>
      </form>
    </div>
  );
}
