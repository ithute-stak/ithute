"use client";

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  ChevronDown,
  Eraser,
  IndentDecrease,
  IndentIncrease,
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
import { stripHtml, textToHtml, webmail } from "./mail-types";

type Props = {
  address: string;
  compose: ComposeState;
  setCompose: React.Dispatch<React.SetStateAction<ComposeState>>;
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
  trailing?: React.ReactNode;
};

function ToolButton({ title, children, onClick }: { title: string; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-[#44546a] hover:bg-[#e8edf5] hover:text-[#1f2937]"
    >
      {children}
    </button>
  );
}

function recipientAddress(value: string) {
  const trimmed = value.trim();
  const angle = trimmed.match(/<([^>]+)>/);
  return (angle?.[1] || trimmed).trim();
}

function recipientList(value: string) {
  return value
    .split(/[;,\n]/)
    .map(recipientAddress)
    .filter(Boolean);
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
    if (term.length < 2) {
      setContacts([]);
      setContactOpen(false);
      return;
    }
    const timer = window.setTimeout(() => {
      void webmail(`/contacts?q=${encodeURIComponent(term)}`)
        .then(async (response) => (response.ok ? response.json() : { items: [] }))
        .then((payload) => {
          const items = ((payload.items || []) as Contact[]).filter((contact) => !tokens.some((token) => token.toLowerCase() === contact.email.toLowerCase())).slice(0, 7);
          setContacts(items);
          setContactOpen(Boolean(items.length));
        })
        .catch(() => undefined);
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
    setTokens(nextTokens);
    setDraft("");
    setContactOpen(false);
    emit(nextTokens);
  }

  function remove(index: number) {
    const nextTokens = tokens.filter((_, tokenIndex) => tokenIndex !== index);
    setTokens(nextTokens);
    emit(nextTokens, draft);
  }

  function onDraftChange(nextDraft: string) {
    setDraft(nextDraft);
    emit(tokens, nextDraft);
  }

  return (
    <div className="relative flex min-h-11 items-start border-b border-[#e5e7eb] py-1.5">
      <span className="w-12 shrink-0 pt-1.5 text-xs font-semibold text-[#5b6575]">{label}</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {tokens.map((token, index) => (
          <span key={`${token}-${index}`} className="inline-flex max-w-full items-center gap-1 rounded-full border border-[#c9d6eb] bg-[#eef4ff] py-1 pl-2.5 pr-1 text-xs font-medium text-[#244a7c]">
            <span className="max-w-[220px] truncate">{token}</span>
            <button type="button" onClick={() => remove(index)} className="grid h-5 w-5 place-items-center rounded-full hover:bg-[#dce8fb]" aria-label={`Remove ${token}`}><X size={12} /></button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onFocus={() => setContactOpen(Boolean(contacts.length))}
          onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === "Tab" || event.key === "," || event.key === ";") && draft.trim()) {
              event.preventDefault();
              add(recipientList(draft));
            } else if (event.key === "Backspace" && !draft && tokens.length) {
              const nextTokens = tokens.slice(0, -1);
              const last = tokens[tokens.length - 1];
              setTokens(nextTokens);
              setDraft(last);
              emit(nextTokens, last);
            }
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData.getData("text");
            if (!/[;,\n]/.test(pasted)) return;
            event.preventDefault();
            add(recipientList(pasted));
          }}
          className="min-w-[150px] flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-[#8a94a3]"
          placeholder={tokens.length ? "" : placeholder}
          autoComplete="off"
          required={required && tokens.length === 0}
          aria-label={`${label} recipients`}
        />
      </div>
      {trailing ? <div className="ml-2 shrink-0 pt-1">{trailing}</div> : null}
      {contactOpen ? (
        <div className="absolute left-12 right-0 top-full z-30 mt-1 overflow-hidden rounded-xl border border-[#cfd6df] bg-white py-1 shadow-[0_14px_36px_rgba(15,23,42,.16)]">
          {contacts.map((contact) => (
            <button key={contact.email} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => add([contact.email])} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-[#f1f5fb]">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#dce8fb] text-xs font-bold text-[#315b8c]">{(contact.name || contact.email)[0]?.toUpperCase()}</span>
              <span className="min-w-0"><span className="block truncate text-sm font-medium text-[#202124]">{contact.name || contact.email}</span><span className="block truncate text-xs text-[#6b7280]">{contact.email}</span></span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function MailCompose({
  address,
  compose,
  setCompose,
  loading,
  minimized,
  expanded,
  showCcBcc,
  signatureHtml,
  onMinimized,
  onExpanded,
  onShowCcBcc,
  onClose,
  onDiscard,
  onSaveDraft,
  onSend,
  onAttach,
}: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<Range | null>(null);
  const [formatOpen, setFormatOpen] = useState(true);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || document.activeElement === editor) return;
    const desired = compose.bodyHtml || textToHtml(compose.bodyText);
    if (editor.innerHTML !== desired) editor.innerHTML = desired;
  }, [compose.bodyHtml, compose.bodyText]);

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

  function restoreSelection() {
    const editor = editorRef.current;
    const selection = window.getSelection();
    editor?.focus();
    if (!selection || !selectionRef.current) return;
    selection.removeAllRanges();
    selection.addRange(selectionRef.current);
  }

  function exec(command: string, value?: string) {
    restoreSelection();
    document.execCommand(command, false, value);
    rememberSelection();
    syncEditor();
  }

  function addLink() {
    const url = window.prompt("Paste a link");
    if (!url) return;
    exec("createLink", url);
  }

  const ccBccToggle = (
    <button type="button" onClick={() => onShowCcBcc(!showCcBcc)} className="rounded-md px-2 py-1 text-xs font-semibold text-[#4f6076] hover:bg-[#edf2f8]">{showCcBcc ? "Hide Cc/Bcc" : "Cc Bcc"}</button>
  );

  return (
    <div className={`fixed z-[80] ${expanded ? "inset-0 flex items-center justify-center bg-black/30 p-3 sm:p-6" : "bottom-0 right-0 sm:right-5"}`}>
      <form
        onSubmit={onSend}
        className={`mail-compose-window flex overflow-hidden bg-white shadow-2xl ${
          expanded
            ? "h-[94vh] w-full max-w-6xl rounded-2xl"
            : minimized
              ? "h-11 w-[min(94vw,470px)] rounded-t-xl"
              : "h-[min(780px,calc(100vh-70px))] w-[min(100vw,780px)] rounded-t-xl"
        }`}
      >
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-11 shrink-0 items-center border-b border-[#dfe4ea] bg-[#eef3f9] px-3 sm:px-4">
            <p className="min-w-0 flex-1 truncate text-[13px] font-semibold text-[#263548]">New Message</p>
            <div className="flex items-center gap-0.5">
              <ToolButton title={minimized ? "Restore" : "Minimize"} onClick={() => onMinimized(!minimized)}>{minimized ? <Maximize2 size={14} /> : <Minimize2 size={14} />}</ToolButton>
              <ToolButton title={expanded ? "Exit full screen" : "Full screen"} onClick={() => { onExpanded(!expanded); onMinimized(false); }}><Maximize2 size={14} /></ToolButton>
              <ToolButton title="Save and close" onClick={onClose}><X size={16} /></ToolButton>
            </div>
          </div>

          {!minimized ? (
            <>
              <div className="shrink-0 bg-white px-3 sm:px-4">
                <RecipientField
                  label="To"
                  value={compose.to}
                  onChange={(value) => setCompose((current) => ({ ...current, to: value }))}
                  placeholder="Type a name or email, then press Enter"
                  required
                  trailing={ccBccToggle}
                />
                {showCcBcc ? (
                  <>
                    <RecipientField label="Cc" value={compose.cc} onChange={(value) => setCompose((current) => ({ ...current, cc: value }))} placeholder="Add one or more Cc recipients" />
                    <RecipientField label="Bcc" value={compose.bcc} onChange={(value) => setCompose((current) => ({ ...current, bcc: value }))} placeholder="Add one or more Bcc recipients" />
                  </>
                ) : null}
                <label className="flex min-h-11 items-center border-b border-[#e5e7eb]"><span className="w-12 shrink-0 text-xs font-semibold text-[#5b6575]">Subject</span><input value={compose.subject} onChange={(event) => setCompose((current) => ({ ...current, subject: event.target.value }))} className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none" placeholder="Subject" /></label>
              </div>

              {formatOpen ? (
                <div className="mail-word-ribbon shrink-0 border-b border-[#d9e0e8] bg-[#f8fafc]">
                  <div className="flex h-8 items-end gap-4 border-b border-[#e2e7ed] px-3 text-xs font-semibold text-[#4a5a70]">
                    <span className="border-b-2 border-[#2f5597] px-1 pb-1 text-[#2f5597]">Home</span>
                    <span className="pb-1 text-[#7b8796]">Message</span>
                  </div>
                  <div className="flex min-h-12 items-center gap-1 overflow-x-auto px-2 py-1.5 sm:px-3">
                    <select aria-label="Font family" defaultValue="Arial" onChange={(event) => exec("fontName", event.target.value)} className="h-8 w-28 shrink-0 rounded border border-[#cbd5e1] bg-white px-2 text-xs text-[#263548] outline-none focus:border-[#7396c8]">
                      <option>Arial</option><option>Calibri</option><option>Georgia</option><option>Tahoma</option><option>Times New Roman</option><option>Verdana</option>
                    </select>
                    <select aria-label="Font size" defaultValue="3" onChange={(event) => exec("fontSize", event.target.value)} className="h-8 w-16 shrink-0 rounded border border-[#cbd5e1] bg-white px-1.5 text-xs text-[#263548] outline-none focus:border-[#7396c8]">
                      <option value="2">10</option><option value="3">12</option><option value="4">14</option><option value="5">18</option><option value="6">24</option><option value="7">32</option>
                    </select>
                    <span className="mx-1 h-7 w-px shrink-0 bg-[#d8dee7]" />
                    <ToolButton title="Bold" onClick={() => exec("bold")}><Bold size={15} /></ToolButton>
                    <ToolButton title="Italic" onClick={() => exec("italic")}><Italic size={15} /></ToolButton>
                    <ToolButton title="Underline" onClick={() => exec("underline")}><Underline size={15} /></ToolButton>
                    <label title="Font color" className="relative grid h-8 w-8 shrink-0 cursor-pointer place-items-center rounded-md text-sm font-bold text-[#44546a] hover:bg-[#e8edf5]">A<span className="absolute bottom-1 h-[2px] w-4 bg-[#c62828]" /><input type="color" defaultValue="#202124" className="absolute inset-0 cursor-pointer opacity-0" onChange={(event) => exec("foreColor", event.target.value)} /></label>
                    <ToolButton title="Clear formatting" onClick={() => exec("removeFormat")}><Eraser size={15} /></ToolButton>
                    <span className="mx-1 h-7 w-px shrink-0 bg-[#d8dee7]" />
                    <ToolButton title="Align left" onClick={() => exec("justifyLeft")}><AlignLeft size={15} /></ToolButton>
                    <ToolButton title="Align center" onClick={() => exec("justifyCenter")}><AlignCenter size={15} /></ToolButton>
                    <ToolButton title="Align right" onClick={() => exec("justifyRight")}><AlignRight size={15} /></ToolButton>
                    <ToolButton title="Bulleted list" onClick={() => exec("insertUnorderedList")}><List size={15} /></ToolButton>
                    <ToolButton title="Numbered list" onClick={() => exec("insertOrderedList")}><ListOrdered size={15} /></ToolButton>
                    <ToolButton title="Decrease indent" onClick={() => exec("outdent")}><IndentDecrease size={15} /></ToolButton>
                    <ToolButton title="Increase indent" onClick={() => exec("indent")}><IndentIncrease size={15} /></ToolButton>
                    <ToolButton title="Quote" onClick={() => exec("formatBlock", "blockquote")}><Quote size={15} /></ToolButton>
                    <span className="mx-1 h-7 w-px shrink-0 bg-[#d8dee7]" />
                    <ToolButton title="Insert link" onClick={addLink}><Link2 size={15} /></ToolButton>
                    <ToolButton title="Undo" onClick={() => exec("undo")}><Undo2 size={15} /></ToolButton>
                    <ToolButton title="Redo" onClick={() => exec("redo")}><Redo2 size={15} /></ToolButton>
                  </div>
                </div>
              ) : null}

              <div className="relative min-h-0 flex-1 overflow-y-auto bg-[#eef1f5] p-2.5 sm:p-4">
                <div className="mx-auto min-h-full max-w-[860px] border border-[#dde2e8] bg-white shadow-[0_2px_10px_rgba(15,23,42,.08)]">
                  <div
                    ref={editorRef}
                    contentEditable
                    suppressContentEditableWarning
                    role="textbox"
                    aria-multiline="true"
                    aria-label="Message body"
                    onInput={() => { syncEditor(); rememberSelection(); }}
                    onMouseUp={rememberSelection}
                    onKeyUp={rememberSelection}
                    onFocus={rememberSelection}
                    data-placeholder="Write your message"
                    className="mail-rich-editor min-h-[360px] px-5 py-5 text-sm leading-6 text-[#202124] outline-none sm:px-7 sm:py-6"
                  />
                  {signatureHtml ? <div className="pointer-events-none mx-5 mb-6 border-t border-transparent pt-2 text-sm text-[#5f6368] sm:mx-7" dangerouslySetInnerHTML={{ __html: signatureHtml }} /> : null}
                </div>
              </div>

              {compose.attachments.length ? (
                <div className="flex max-h-24 shrink-0 flex-wrap gap-2 overflow-y-auto border-t border-[#dfe4ea] bg-white px-4 py-2">
                  {compose.attachments.map((attachment, index) => (
                    <button type="button" key={`${attachment.filename}-${index}`} onClick={() => setCompose((current) => ({ ...current, attachments: current.attachments.filter((_, itemIndex) => itemIndex !== index) }))} className="flex max-w-[260px] items-center gap-2 rounded-lg border border-[#cfd6df] bg-[#f8fafc] px-2.5 py-1.5 text-xs font-medium hover:bg-[#eef2f6]" title="Remove attachment"><Paperclip size={12} /><span className="truncate">{attachment.filename}</span><X size={12} /></button>
                  ))}
                </div>
              ) : null}

              <div className="shrink-0 border-t border-[#d9e0e8] bg-white px-2 py-2 sm:px-3">
                <div className="flex items-center gap-1">
                  <div className="flex overflow-hidden rounded-md bg-[#2f5597] text-white shadow-sm hover:bg-[#244779]">
                    <button disabled={loading} type="submit" className="flex min-h-9 items-center gap-2 px-5 text-sm font-semibold disabled:opacity-60"><Send size={15} />{loading ? "Sending…" : "Send"}</button>
                    <button type="button" className="grid w-8 place-items-center border-l border-white/25" title="Send options"><ChevronDown size={14} /></button>
                  </div>
                  <button type="button" onClick={() => setFormatOpen((value) => !value)} className={`grid h-9 w-9 place-items-center rounded-md hover:bg-[#edf2f8] ${formatOpen ? "bg-[#e8eef8] text-[#2f5597]" : "text-[#5f6368]"}`} title="Formatting ribbon"><span className="text-[15px] font-semibold underline underline-offset-2">A</span></button>
                  <label className="grid h-9 w-9 cursor-pointer place-items-center rounded-md text-[#5f6368] hover:bg-[#edf2f8]" title="Attach files"><Paperclip size={17} /><input type="file" multiple className="hidden" onChange={(event) => onAttach(event.target.files)} /></label>
                  <button type="button" onClick={onSaveDraft} className="hidden rounded-md px-3 py-2 text-xs font-medium text-[#5f6368] hover:bg-[#edf2f8] sm:block">Save draft</button>
                  <span className="ml-1 hidden max-w-[220px] truncate text-[10px] text-[#80868b] lg:block">From {address}</span>
                  <button type="button" onClick={onDiscard} className="ml-auto grid h-9 w-9 place-items-center rounded-md text-[#5f6368] hover:bg-[#edf2f8]" title="Discard"><Trash2 size={16} /></button>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </form>
    </div>
  );
}
