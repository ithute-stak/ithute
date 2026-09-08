"use client";

import Link from "next/link";
import { ChangeEvent, useCallback, useEffect, useState } from "react";
import styles from "../workforce/workforce.module.css";

type Row = Record<string, unknown>;
type Mode = "procurement" | "tenders";
const API = "/api/v1";
const text = (row: Row | null | undefined, key: string) => String(row?.[key] ?? "");
const number = (row: Row | null | undefined, key: string) => Number(row?.[key] ?? 0);
const rows = (value: unknown): Row[] => Array.isArray(value) ? value as Row[] : [];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { ...init, credentials: "include", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  if (response.status === 401) { window.location.href = "/login?returnTo=" + encodeURIComponent("/assistants"); throw new Error("Session expired"); }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail ?? payload));
  return payload as T;
}

function JsonResult({ value }: { value: Row | null }) {
  if (!value) return <div className={styles.empty}>Run a rule-based check to see its transparent result here.</div>;
  return <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0, fontSize: 12, lineHeight: 1.6, color: "#163b36" }}>{JSON.stringify(value, null, 2)}</pre>;
}

export default function AlgorithmicAssistantsPage() {
  const [mode, setMode] = useState<Mode>("procurement");
  const [requisitions, setRequisitions] = useState<Row[]>([]);
  const [tenders, setTenders] = useState<Row[]>([]);
  const [documents, setDocuments] = useState<Row[]>([]);
  const [locations, setLocations] = useState<Row[]>([]);
  const [requisitionId, setRequisitionId] = useState("");
  const [tenderId, setTenderId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [question, setQuestion] = useState("");
  const [draftKind, setDraftKind] = useState("cover_letter");
  const [result, setResult] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [reqs, tenderRows, catalog] = await Promise.all([api<Row[]>("/procurement/requisitions"), api<Row[]>("/tenders"), api<{ documents: Row[]; locations: Row[] }>("/procurement/catalog")]);
      setRequisitions(reqs); setTenders(tenderRows); setDocuments(catalog.documents); setLocations(catalog.locations);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load assistant data. Initialise Procurement and Tender Management first."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  function done(message: string, data?: unknown) { setNotice(message); setError(""); if (data && typeof data === "object") setResult(data as Row); setTimeout(() => setNotice(""), 4500); void refresh(); }
  async function run(path: string, init?: RequestInit, message = "Rule-based analysis completed.") { try { const data = await api<Row>(path, init); done(message, data.result ?? data); } catch (reason) { setError(reason instanceof Error ? reason.message : "Assistant action failed."); } }
  function selectedTender() { return tenders.find(row => String(row.id) === tenderId) ?? null; }
  function sourcePayload() { return { document_id: documentId ? Number(documentId) : null, source_text: sourceText.trim() || null }; }

  async function uploadSource(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; const tender = selectedTender();
    if (!file || !tender) return;
    try {
      const created = await api<Row>("/foundation/documents", { method: "POST", body: JSON.stringify({ branch_id: number(tender, "branch_id") || null, site_id: tender.site_id ? number(tender, "site_id") : null, title: file.name, category: "tender_source_document", entity_type: "tender", entity_id: tenderId, confidentiality: "internal", created_by: "Algorithmic assistant workspace" }) });
      const body = new FormData(); body.set("file", file); body.set("uploaded_by", "Algorithmic assistant workspace"); body.set("note", "Source for deterministic tender-document review");
      const response = await fetch(API + "/foundation/documents/" + created.id + "/versions", { method: "POST", credentials: "include", body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not upload the document");
      setDocumentId(String(created.id)); setSourceText(""); done("Document uploaded and ready for deterministic tender review.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Document upload failed."); }
  }

  if (loading) return <main className={styles.page}><div className={styles.loading}><strong>Loading Algorithmic Assistants…</strong></div></main>;
  return <main className={styles.page}><header className={styles.header}><div className={styles.brand}><div className={styles.brandMark}>BT</div><div><small>BuildTrack Phase 10</small><h1>Algorithmic Assistants</h1><p>Explainable rules and document extraction — no AI model, no automatic decisions.</p></div></div><div className={styles.headerActions}><Link className={styles.link} href="/procurement">Procurement</Link><Link className={styles.link} href="/tenders">Tenders</Link></div></header><div className={styles.shell}>
    {error && <div className={styles.error}>{error}</div>}{notice && <div className={styles.notice}>{notice}</div>}
    <section className={styles.hero}><div className={styles.heroCard}><span className={styles.phase}>Deterministic control layer</span><h2>Fast checks, never unchecked decisions.</h2><p>Every result shows source evidence, rule outputs and its limits. Procurement selections, approvals and submissions stay inside BuildTrack’s controlled workflows.</p></div><div className={styles.heroCard}><small>Engine</small><h2>Rules</h2><p>keyword matching · scoring · extraction · templates</p></div></section>
    <div className={styles.tabs}><button className={mode === "procurement" ? styles.active : ""} onClick={() => { setMode("procurement"); setResult(null); }}>Procurement Assistant</button><button className={mode === "tenders" ? styles.active : ""} onClick={() => { setMode("tenders"); setResult(null); }}>Tender Assistant</button></div>
    {mode === "procurement" && <section className={styles.grid2}><div className={styles.panel}><h3>Purchase request and quotation tools</h3><div className={styles.form}><label>Requisition<select value={requisitionId} onChange={event => setRequisitionId(event.target.value)}><option value="">Select</option>{requisitions.map(row => <option key={String(row.id)} value={String(row.id)}>{text(row, "requisition_number")} · {text(row, "title")}</option>)}</select></label><div className={styles.formActions}><button className={styles.button} disabled={!requisitionId} onClick={() => void run("/assistants/procurement/requisitions/" + requisitionId + "/review", { method: "POST" }, "Purchase request reviewed.")}>Review request</button><button className={styles.button} disabled={!requisitionId} onClick={() => void run("/assistants/procurement/requisitions/" + requisitionId + "/quotation-comparison", { method: "POST" }, "Quotation comparison prepared.")}>Compare quotations</button></div><label>Delivery location for PO draft<select value={locationId} onChange={event => setLocationId(event.target.value)}><option value="">Select</option>{locations.map(row => <option key={String(row.id)} value={String(row.id)}>{text(row, "code")} · {text(row, "name")}</option>)}</select></label><div className={styles.formActions}><button className={styles.button} disabled={!requisitionId || !locationId} onClick={() => void run("/assistants/procurement/requisitions/" + requisitionId + "/purchase-order-draft?delivery_location_id=" + locationId, undefined, "Purchase-order draft prepared.")}>Prepare PO draft</button></div></div><p>For quotation comparison, first upload each PDF/DOCX in Documents and attach it to the recorded supplier quotation. The rule engine reads price, delivery, warranty and payment terms where the document contains readable text.</p></div><div className={styles.panel}><h3>Supplier knowledge and policy</h3><div className={styles.form}><label>Ask about suppliers or policy<input placeholder="Which supplier supplied cement last year?" value={question} onChange={event => setQuestion(event.target.value)}/></label><div className={styles.formActions}><button className={styles.button} disabled={question.trim().length < 3} onClick={() => void run("/assistants/procurement/supplier-knowledge?question=" + encodeURIComponent(question), undefined, "Supplier history checked.")}>Supplier answer</button><button className={styles.button} disabled={question.trim().length < 3} onClick={() => void run("/assistants/procurement/policy-answer?question=" + encodeURIComponent(question), undefined, "Procurement policy answered.")}>Policy answer</button></div></div><p>Examples: “Which supplier offers the best warranty?”, “Which supplier has the lowest average price for cement?”, “How many quotations are required?”</p></div><div className={styles.panel} style={{ gridColumn: "1 / -1" }}><h3>Transparent procurement result</h3><JsonResult value={result}/></div></section>}
    {mode === "tenders" && <section className={styles.grid2}><div className={styles.panel}><h3>Tender compliance and checklist</h3><div className={styles.form}><label>Tender<select value={tenderId} onChange={event => setTenderId(event.target.value)}><option value="">Select</option>{tenders.map(row => <option key={String(row.id)} value={String(row.id)}>{text(row, "tender_number")} · {text(row, "title")}</option>)}</select></label><label>Uploaded source document<select value={documentId} onChange={event => setDocumentId(event.target.value)}><option value="">Select PDF/DOCX/TXT source</option>{documents.map(row => <option key={String(row.id)} value={String(row.id)}>{text(row, "title")}</option>)}</select></label><label>Upload tender PDF/DOCX<input type="file" accept=".pdf,.docx,.txt,.csv,.md,.json" disabled={!tenderId} onChange={event => void uploadSource(event)}/></label><label className={styles.wide}>Or paste tender text<textarea value={sourceText} onChange={event => setSourceText(event.target.value)} placeholder="Paste tender instructions where a source document is not available…"/></label><div className={styles.formActions}><button className={styles.button} disabled={!tenderId || (!documentId && !sourceText.trim())} onClick={() => void run("/assistants/tenders/" + tenderId + "/document-review", { method: "POST", body: JSON.stringify(sourcePayload()) }, "Tender document reviewed.")}>Check compliance</button><button className={styles.button} disabled={!tenderId || (!documentId && !sourceText.trim())} onClick={() => void run("/assistants/tenders/" + tenderId + "/checklist-generate", { method: "POST", body: JSON.stringify(sourcePayload()) }, "Tender checklist generated.")}>Generate checklist</button></div></div><p>PDF, DOCX and readable text documents are extracted with deterministic parsers. Generated checklist entries remain missing until staff attach and verify controlled evidence.</p></div><div className={styles.panel}><h3>Questions, drafts and reminders</h3><div className={styles.form}><label>Question<input placeholder="Is a bid bond required?" value={question} onChange={event => setQuestion(event.target.value)}/></label><div className={styles.formActions}><button className={styles.button} disabled={!tenderId || question.trim().length < 3} onClick={() => void run("/assistants/tenders/" + tenderId + "/question?question=" + encodeURIComponent(question) + (documentId ? "&document_id=" + documentId : ""), undefined, "Tender question answered from reviewed evidence.")}>Ask tender</button><button className={styles.button} disabled={!tenderId} onClick={() => void run("/assistants/tenders/" + tenderId + "/deadline-reminders", undefined, "Deadline reminders prepared.")}>Show 30/14/7/1 reminders</button></div><label>Draft template<select value={draftKind} onChange={event => setDraftKind(event.target.value)}><option value="cover_letter">Cover letter</option><option value="company_profile">Company profile</option><option value="technical_response">Technical response</option><option value="method_statement">Method statement</option></select></label><div className={styles.formActions}><button className={styles.button} disabled={!tenderId} onClick={() => void run("/assistants/tenders/" + tenderId + "/draft", { method: "POST", body: JSON.stringify({ kind: draftKind, document_id: documentId ? Number(documentId) : null }) }, "Controlled draft template prepared.")}>Prepare draft</button></div></div><p>Run a document review first before asking questions. Drafts use tender facts and placeholders only; they must be reviewed, edited and saved through document control before submission.</p></div><div className={styles.panel} style={{ gridColumn: "1 / -1" }}><h3>Transparent tender result</h3><JsonResult value={result}/></div></section>}
  </div></main>;
}
