"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, FileText, Landmark, ShieldCheck } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const money = (minor = 0) => `M ${(minor / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

type Invoice = { id: string; invoice_number: string; description: string; due_date: string; status: string; total_minor: number; paid_minor: number; outstanding_minor: number };
type Portal = { client: { name: string; email: string; address: string; phone: string }; summary: { current_exposure_minor: number; open_overdue_invoice_count: number }; invoices: Invoice[] };

export default function FinancePortalPage() {
  const [token, setToken] = useState(""); const [data, setData] = useState<Portal | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  useEffect(() => {
    const raw = window.location.hash.startsWith("#token=") ? decodeURIComponent(window.location.hash.slice(7)) : "";
    setToken(raw);
    if (!raw) { setError("This secure Finance link is missing or invalid."); setLoading(false); return; }
    void fetch(`${API}/finance/portal/me`, { headers: { "X-Finance-Portal-Token": raw } }).then(async (r) => { const body = await r.json().catch(() => ({})); if (!r.ok) throw new Error(String(body.detail || "Unable to open Finance portal")); setData(body); }).catch((e) => setError(e instanceof Error ? e.message : "Unable to open Finance portal")).finally(() => setLoading(false));
  }, []);

  const overdue = useMemo(() => data?.invoices.filter((i) => i.status === "overdue") || [], [data]);

  async function download(path: string, filename: string) {
    if (!token) return;
    const r = await fetch(`${API}${path}`, { headers: { "X-Finance-Portal-Token": token } });
    if (!r.ok) { setError("Unable to download the requested document."); return; }
    const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }

  return <main className="min-h-screen bg-[#f3f7f5] px-4 py-8 text-[#17352d]">
    <div className="mx-auto max-w-5xl space-y-4">
      <header className="rounded-3xl border border-[#c9ddd5] bg-white p-6 shadow-sm"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#123f35] text-white"><ShieldCheck size={20} /></div><div><p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#5f8177]">Secure client access</p><h1 className="text-2xl font-black">Ithute Finance Portal</h1></div></div></header>
      {loading ? <section className="rounded-3xl border bg-white p-8 text-sm font-bold">Opening your secure Finance workspace…</section> : error ? <section className="rounded-3xl border border-red-200 bg-white p-8 text-sm font-bold text-red-700">{error}</section> : data ? <>
        <section className="rounded-3xl border border-[#c9ddd5] bg-white p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-[10px] font-black uppercase tracking-[0.16em] text-[#5f8177]">Account</p><h2 className="mt-1 text-xl font-black">{data.client.name}</h2><p className="mt-1 text-xs text-[#667c74]">{data.client.email}</p>{data.client.address ? <p className="text-xs text-[#667c74]">{data.client.address}</p> : null}</div><button onClick={() => void download("/finance/portal/statement.pdf", "Ithute-Statement.pdf")} className="rounded-xl bg-[#123f35] px-4 py-2.5 text-xs font-black text-white"><Download size={14} className="mr-2 inline" />Download statement</button></div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Outstanding</p><p className="mt-2 text-xl font-black">{money(data.summary.current_exposure_minor)}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Overdue invoices</p><p className="mt-2 text-xl font-black">{data.summary.open_overdue_invoice_count}</p></div><div className="rounded-2xl border p-4"><p className="text-[10px] font-black uppercase">Documents</p><p className="mt-2 text-xl font-black">{data.invoices.length}</p></div></div>
        </section>
        {overdue.length ? <section className="rounded-3xl border border-amber-200 bg-amber-50 p-5 text-xs font-bold">You currently have {overdue.length} overdue invoice{overdue.length === 1 ? "" : "s"}. Please use the invoice number or client name as your payment reference.</section> : null}
        <section className="overflow-hidden rounded-3xl border border-[#c9ddd5] bg-white"><div className="border-b p-5"><div className="flex items-center gap-2"><Landmark size={17} /><h2 className="font-black">Invoices</h2></div></div><div className="overflow-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-3">Invoice</th><th className="p-3">Description</th><th className="p-3">Due</th><th className="p-3">Status</th><th className="p-3 text-right">Total</th><th className="p-3 text-right">Paid</th><th className="p-3 text-right">Outstanding</th><th className="p-3">PDF</th></tr></thead><tbody>{data.invoices.map((row) => <tr key={row.id} className="border-t"><td className="p-3 font-black">{row.invoice_number}</td><td className="p-3">{row.description}</td><td className="p-3">{row.due_date}</td><td className="p-3 uppercase">{row.status}</td><td className="p-3 text-right">{money(row.total_minor)}</td><td className="p-3 text-right">{money(row.paid_minor)}</td><td className="p-3 text-right font-black">{money(row.outstanding_minor)}</td><td className="p-3"><button onClick={() => void download(`/finance/portal/invoices/${row.id}/pdf`, `${row.invoice_number}.pdf`)} className="font-black underline"><FileText size={13} className="mr-1 inline" />PDF</button></td></tr>)}</tbody></table></div></section>
      </> : null}
    </div>
  </main>;
}
