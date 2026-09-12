"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  AtSign,
  Bold,
  CheckCircle2,
  ContactRound,
  ImagePlus,
  Italic,
  Mail,
  Palette,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Underline,
  UserRound,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
type Contact = { email: string; name: string; sources?: string[]; last_seen?: string; interactions?: number };
type Identity = { address: string; display_name: string };
type Density = "comfortable" | "compact";

async function wm(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function contactSource(contact: Contact) {
  const sources = new Set(contact.sources || []);
  if (sources.has("incoming") && sources.has("outgoing")) return "Incoming + outgoing";
  if (sources.has("incoming")) return "Incoming mail";
  if (sources.has("outgoing")) return "Outgoing mail";
  return "Saved contact";
}

function contactSourceTone(contact: Contact) {
  const sources = new Set(contact.sources || []);
  if (sources.has("incoming") && sources.has("outgoing")) return "bg-[#e8f3ee] text-[#174c3f]";
  if (sources.has("incoming")) return "bg-[#eef3fb] text-[#315b8a]";
  if (sources.has("outgoing")) return "bg-[#f7f0da] text-[#75601f]";
  return "bg-[#f1f3f4] text-[#5f6368]";
}

function lastSeen(value?: string) {
  if (!value) return "Previously saved";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Previously saved";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

async function prepareSignatureImage(file: File) {
  if (!file.type.startsWith("image/")) throw new Error("Choose an image file.");
  if (file.size > 5 * 1024 * 1024) throw new Error("Signature images must be smaller than 5 MB.");
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Unable to read that image."));
      image.src = objectUrl;
    });

    let width = Math.max(1, image.naturalWidth);
    let height = Math.max(1, image.naturalHeight);
    const scale = Math.min(1, 360 / width, 140 / height);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));

    for (let attempt = 0; attempt < 8; attempt += 1) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Your browser cannot prepare this image.");
      context.drawImage(image, 0, 0, width, height);
      const quality = Math.max(0.28, 0.82 - attempt * 0.09);
      const value = canvas.toDataURL("image/webp", quality);
      if (value.length <= 12000) return value;
      width = Math.max(80, Math.round(width * 0.82));
      height = Math.max(32, Math.round(height * 0.82));
    }
    throw new Error("That image is too detailed for an email signature. Try a simpler logo or signature image.");
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export default function WebmailSettings() {
  const signatureEditor = useRef<HTMLDivElement>(null);
  const signatureReady = useRef(false);
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [signature, setSignature] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactQuery, setContactQuery] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [imageLoading, setImageLoading] = useState(false);
  const [density, setDensity] = useState<Density>("comfortable");

  async function refreshContacts(triggerDiscovery = false) {
    setContactsLoading(true);
    try {
      if (triggerDiscovery) await wm("/folder-counts").catch(() => null);
      const response = await wm("/contacts");
      if (response.ok) setContacts((await response.json()).items || []);
    } finally {
      setContactsLoading(false);
    }
  }

  async function load() {
    setLoading(true);
    setError("");
    const [session, identity, sig] = await Promise.all([wm("/session"), wm("/identity"), wm("/signature")]);
    if (!session.ok) {
      setError("Your webmail session has expired. Sign in again.");
      setLoading(false);
      return;
    }
    const sessionData = await session.json();
    setAddress(sessionData.address || "");
    if (identity.ok) {
      const data: Identity = await identity.json();
      setDisplayName(data.display_name || "");
      setAddress(data.address || sessionData.address || "");
    }
    if (sig.ok) setSignature((await sig.json()).html || "");
    if (typeof window !== "undefined") setDensity((window.localStorage.getItem("ithute-webmail-density") as Density) || "comfortable");
    await refreshContacts(true);
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!loading && signatureEditor.current && !signatureReady.current) {
      signatureEditor.current.innerHTML = signature;
      signatureReady.current = true;
    }
  }, [loading, signature]);

  async function saveIdentity(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");
    const response = await wm("/identity", { method: "PUT", body: JSON.stringify({ display_name: displayName }) });
    if (response.ok) {
      const data = await response.json();
      setDisplayName(data.display_name || "");
      setMessage("Sender identity saved. New messages will use this display name.");
    } else setError((await response.json().catch(() => ({}))).detail || "Unable to save sender identity.");
  }

  async function saveSignature(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");
    const html = signatureEditor.current?.innerHTML || signature;
    if (html.length > 19000) {
      setError("The signature is too large. Remove an image or shorten the signature and try again.");
      return;
    }
    const response = await wm("/signature", { method: "PUT", body: JSON.stringify({ html }) });
    if (response.ok) {
      const data = await response.json();
      setSignature(data.html || "");
      if (signatureEditor.current) signatureEditor.current.innerHTML = data.html || "";
      setMessage("Signature saved. It will be added automatically to rich messages.");
    } else setError((await response.json().catch(() => ({}))).detail || "Unable to save signature.");
  }

  function updateSignatureState() {
    setSignature(signatureEditor.current?.innerHTML || "");
  }

  function formatSignature(command: "bold" | "italic" | "underline") {
    signatureEditor.current?.focus();
    document.execCommand(command, false);
    updateSignatureState();
  }

  async function addSignatureImage(file?: File) {
    if (!file) return;
    setError("");
    setImageLoading(true);
    try {
      const dataUrl = await prepareSignatureImage(file);
      const editor = signatureEditor.current;
      if (!editor) return;
      editor.insertAdjacentHTML("beforeend", `<p><img src="${dataUrl}" alt="Signature image" width="180"></p>`);
      updateSignatureState();
      setMessage("Signature image added. Save the signature when you are happy with the preview.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to add signature image.");
    } finally {
      setImageLoading(false);
    }
  }

  function removeSignatureImages() {
    signatureEditor.current?.querySelectorAll("img").forEach((image) => image.remove());
    updateSignatureState();
    setMessage("Signature images removed. Save the signature to keep this change.");
  }

  function clearSignature() {
    if (signatureEditor.current) signatureEditor.current.innerHTML = "";
    setSignature("");
    setMessage("Signature cleared in the editor. Save to apply the change.");
  }

  function chooseDensity(value: Density) {
    setDensity(value);
    if (typeof window !== "undefined") window.localStorage.setItem("ithute-webmail-density", value);
    setMessage("Inbox density preference saved on this device.");
  }

  const filteredContacts = useMemo(() => {
    const q = contactQuery.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((contact) => `${contact.name} ${contact.email}`.toLowerCase().includes(q));
  }, [contactQuery, contacts]);

  return (
    <main className="min-h-screen bg-[#f5f7f6] text-[#1f2926]">
      <header className="sticky top-0 z-20 flex h-16 items-center border-b border-[#dde4e0] bg-white/95 px-4 backdrop-blur sm:px-6">
        <Link href="/webmail" className="grid h-10 w-10 place-items-center rounded-full text-[#41504b] hover:bg-[#edf2ef]" aria-label="Back to webmail"><ArrowLeft size={19} /></Link>
        <div className="ml-2 flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#123a38] text-xs font-black text-[#d8c56a] shadow-sm">!T</div>
          <div className="min-w-0"><p className="truncate text-sm font-semibold text-[#183c37]">!thute Mail</p><p className="text-[10px] font-medium text-[#71807b]">Mailbox settings</p></div>
        </div>
        <div className="ml-auto hidden items-center gap-2 rounded-full bg-[#f1f5f3] px-3 py-1.5 text-xs font-medium text-[#53635d] sm:flex"><ShieldCheck size={14} className="text-[#987f2d]" /> Secure mailbox preferences</div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[228px_1fr] lg:px-6 lg:py-8">
        <aside className="h-fit rounded-2xl border border-[#dde4e0] bg-white p-3 shadow-sm lg:sticky lg:top-24">
          <div className="mb-2 px-3 py-2"><p className="text-[10px] font-bold uppercase tracking-[.15em] text-[#7a8883]">Webmail settings</p></div>
          <a href="#general" className="flex items-center gap-3 rounded-xl bg-[#e7f0ec] px-3 py-2.5 text-sm font-semibold text-[#123a38]"><Settings2 size={17} />General</a>
          <a href="#signature" className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-[#3e4d48] hover:bg-[#f1f5f3]"><Mail size={17} />Signature</a>
          <a href="#contacts" className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-[#3e4d48] hover:bg-[#f1f5f3]"><ContactRound size={17} />Smart contacts</a>
          <a href="#appearance" className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-[#3e4d48] hover:bg-[#f1f5f3]"><Palette size={17} />Appearance</a>
          <div className="mt-4 rounded-xl bg-[#faf8ef] p-3"><div className="flex items-center gap-2 text-xs font-semibold text-[#66551e]"><Sparkles size={14} />!thute smart mail</div><p className="mt-1.5 text-[11px] leading-5 text-[#786d48]">Your mailbox learns useful contacts from normal correspondence while keeping mail delivery independent.</p></div>
        </aside>

        <section className="min-w-0 space-y-5">
          <div className="rounded-2xl border border-[#dfe6e2] bg-[linear-gradient(135deg,#eef5f2_0%,#ffffff_65%)] p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-[.16em] text-[#987f2d]">Personalize !thute Mail</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#183c37] sm:text-3xl">Mailbox settings</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#66756f]">Control how recipients see you, build a professional visual signature, and let your mailbox maintain useful contacts automatically.</p></div>{address ? <div className="max-w-full rounded-full border border-[#dde4e0] bg-white px-3 py-2 text-xs font-medium text-[#53635d] shadow-sm"><span className="truncate">{address}</span></div> : null}</div>
          </div>

          {loading ? <div className="rounded-2xl border border-[#dfe6e2] bg-white p-5 text-sm text-[#6f7e79]">Loading your mailbox settings…</div> : null}
          {message ? <div className="flex items-start gap-2 rounded-xl border border-[#cfe4d8] bg-[#edf7f1] px-4 py-3 text-sm font-medium text-[#285b47]"><CheckCircle2 size={17} className="mt-0.5 shrink-0" />{message}</div> : null}
          {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

          <form id="general" onSubmit={saveIdentity} className="scroll-mt-24 rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#e7f0ec] text-[#123a38]"><UserRound size={19} /></div><div><h2 className="text-base font-semibold text-[#25332f]">Sender identity</h2><p className="mt-0.5 text-xs text-[#72807b]">The name recipients see beside your mailbox address.</p></div></div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="block"><span className="text-xs font-semibold text-[#596862]">Display name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={255} className="mt-1.5 w-full rounded-xl border border-[#cfd8d3] px-3 py-2.5 text-sm outline-none focus:border-[#285b55] focus:ring-1 focus:ring-[#285b55]" placeholder="Your name or company" /></label>
              <label className="block"><span className="text-xs font-semibold text-[#596862]">Email address</span><div className="mt-1.5 flex items-center gap-2 rounded-xl border border-[#e0e6e3] bg-[#f7f9f8] px-3 py-2.5 text-sm text-[#66756f]"><AtSign size={15} /><span className="truncate">{address}</span></div></label>
            </div>
            <div className="mt-4 rounded-xl border border-[#edf0ee] bg-[#f8faf9] p-4"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#7a8883]">Recipient preview</p><p className="mt-2 break-words text-sm font-medium text-[#2d3c37]">{displayName || address}{displayName ? ` <${address}>` : ""}</p></div>
            <button className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#123a38] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#0d2d2b]"><Save size={15} />Save identity</button>
          </form>

          <form id="signature" onSubmit={saveSignature} className="scroll-mt-24 rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#faf5df] text-[#806a22]"><ImagePlus size={19} /></div><div><h2 className="text-base font-semibold text-[#25332f]">Visual signature</h2><p className="mt-0.5 text-xs text-[#72807b]">Create it visually — no HTML or code required.</p></div></div><span className="rounded-full bg-[#edf7f1] px-3 py-1.5 text-[11px] font-semibold text-[#285b47]">Image supported</span></div>

            <div className="mt-5 overflow-hidden rounded-2xl border border-[#d8dfdb] bg-white">
              <div className="flex flex-wrap items-center gap-1 border-b border-[#e8ecea] bg-[#f8faf9] px-2 py-2">
                <button type="button" onMouseDown={(event) => { event.preventDefault(); formatSignature("bold"); }} className="grid h-9 w-9 place-items-center rounded-lg text-[#53635d] hover:bg-[#e9efec]" title="Bold"><Bold size={16} /></button>
                <button type="button" onMouseDown={(event) => { event.preventDefault(); formatSignature("italic"); }} className="grid h-9 w-9 place-items-center rounded-lg text-[#53635d] hover:bg-[#e9efec]" title="Italic"><Italic size={16} /></button>
                <button type="button" onMouseDown={(event) => { event.preventDefault(); formatSignature("underline"); }} className="grid h-9 w-9 place-items-center rounded-lg text-[#53635d] hover:bg-[#e9efec]" title="Underline"><Underline size={16} /></button>
                <div className="mx-1 h-6 w-px bg-[#dce3df]" />
                <label className={`inline-flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${imageLoading ? "pointer-events-none bg-[#f1f3f2] text-[#9aa5a1]" : "text-[#123a38] hover:bg-[#e7f0ec]"}`}><ImagePlus size={15} />{imageLoading ? "Preparing image…" : "Add logo / signature image"}<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={(event) => { void addSignatureImage(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
                <button type="button" onClick={removeSignatureImages} className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-[#697772] hover:bg-[#f1f3f2]" title="Remove images"><Trash2 size={14} />Remove image</button>
              </div>
              <div ref={signatureEditor} contentEditable suppressContentEditableWarning onInput={updateSignatureState} className="min-h-52 px-5 py-4 text-sm leading-6 text-[#2c3935] outline-none empty:before:pointer-events-none empty:before:text-[#9aa5a1] empty:before:content-['Type_your_signature_here…']" aria-label="Visual email signature editor" />
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2 text-xs text-[#71807b]"><ShieldCheck size={14} className="text-[#987f2d]" />Images are compressed for email and the server sanitizes the finished signature.</div><span className={`text-[11px] font-medium ${signature.length > 17000 ? "text-amber-700" : "text-[#899590]"}`}>{Math.min(signature.length, 99999).toLocaleString()} / 19,000</span></div>
            <div className="mt-4 flex flex-wrap items-center gap-3"><button className="inline-flex items-center gap-2 rounded-full bg-[#123a38] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#0d2d2b]"><Save size={15} />Save signature</button><button type="button" onClick={clearSignature} className="rounded-full border border-[#d3dbd7] px-4 py-2.5 text-sm font-medium text-[#53635d] hover:bg-[#f5f7f6]">Clear</button><span className="text-xs text-[#71807b]">Compose uses the saved signature automatically.</span></div>
          </form>

          <section id="contacts" className="scroll-mt-24 rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-3"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#e7f0ec] text-[#123a38]"><Sparkles size={19} /></div><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-base font-semibold text-[#25332f]">Smart contacts</h2><span className="rounded-full bg-[#edf7f1] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-[#285b47]">Automatic</span></div><p className="mt-1 max-w-2xl text-xs leading-5 text-[#72807b]">Contacts are learned automatically from people who email you and people you email. Incoming and outgoing mailbox headers are detected during normal mailbox refreshes, so autocomplete improves without manual data entry.</p></div></div><button type="button" onClick={() => void refreshContacts(true)} disabled={contactsLoading} className="inline-flex items-center gap-2 rounded-full border border-[#d3dbd7] px-4 py-2 text-xs font-semibold text-[#40514b] hover:bg-[#f3f6f4] disabled:opacity-50"><RefreshCw size={14} className={contactsLoading ? "animate-spin" : ""} />Refresh contacts</button></div>

            <div className="mt-5 flex items-center gap-2 rounded-xl border border-[#d7dfdb] bg-[#fafcfb] px-3"><ContactRound size={16} className="text-[#71807b]" /><input value={contactQuery} onChange={(event) => setContactQuery(event.target.value)} className="h-11 min-w-0 flex-1 border-0 bg-transparent text-sm outline-none ring-0" placeholder={`Search ${contacts.length || ""} contacts`} /></div>

            <div className="mt-4 overflow-hidden rounded-2xl border border-[#e3e8e5]">
              {filteredContacts.map((contact) => <div key={contact.email} className="flex flex-wrap items-center gap-3 border-b border-[#edf0ee] px-4 py-3.5 last:border-0 hover:bg-[#fafcfb]"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#e7f0ec] text-xs font-bold text-[#123a38]">{(contact.name || contact.email)[0]?.toUpperCase()}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-[#33413d]">{contact.name || contact.email}</p><p className="truncate text-xs text-[#71807b]">{contact.email}</p></div><div className="ml-auto flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${contactSourceTone(contact)}`}>{contactSource(contact)}</span><span className="hidden text-[10px] text-[#919c98] sm:inline">{lastSeen(contact.last_seen)}</span></div></div>)}
              {!filteredContacts.length ? <div className="px-4 py-10 text-center"><ContactRound className="mx-auto text-[#a1aca8]" size={24} /><p className="mt-3 text-sm font-medium text-[#596862]">{contactQuery ? "No contacts match your search." : "No contacts discovered yet."}</p><p className="mt-1 text-xs text-[#899590]">Open or refresh your mailbox and !thute Mail will learn from recent correspondence.</p></div> : null}
            </div>
          </section>

          <section id="appearance" className="scroll-mt-24 rounded-2xl border border-[#dfe6e2] bg-white p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#faf5df] text-[#806a22]"><Palette size={19} /></div><div><h2 className="text-base font-semibold text-[#25332f]">Inbox density</h2><p className="mt-0.5 text-xs text-[#72807b]">Choose how much vertical space each message uses on this device.</p></div></div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">{(["comfortable", "compact"] as Density[]).map((value) => <button key={value} type="button" onClick={() => chooseDensity(value)} className={`rounded-2xl border p-4 text-left transition ${density === value ? "border-[#285b55] bg-[#f0f6f3] ring-1 ring-[#285b55]" : "border-[#d9e0dc] hover:bg-[#f8faf9]"}`}><div className="flex items-center justify-between"><span className="text-sm font-semibold capitalize text-[#34433e]">{value}</span>{density === value ? <CheckCircle2 size={17} className="text-[#285b55]" /> : null}</div><div className="mt-4 space-y-2"><div className={`${value === "compact" ? "h-2" : "h-3"} rounded bg-[#dfe6e2]`} /><div className={`${value === "compact" ? "h-2" : "h-3"} w-4/5 rounded bg-[#e8edea]`} /></div></button>)}</div>
          </section>
        </section>
      </div>
    </main>
  );
}
