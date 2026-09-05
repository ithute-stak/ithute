"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, BadgeCheck, KeyRound, Loader2, Play, RotateCcw, ShieldCheck, TestTube2 } from "lucide-react";
import { API_URL } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";


type CatalogCase = {
  value?: string;
  expected?: string;
  expected_statuses?: string[];
};

type CatalogService = {
  label: string;
  capability?: string;
  input_field?: string;
  requires_voucher_code?: boolean;
  cases: Record<string, CatalogCase>;
};

type Catalog = {
  provider: string;
  environment: string;
  ready: boolean;
  missing?: string[];
  capabilities?: Record<string, boolean>;
  services: Record<string, CatalogService>;
};

type PortalContext = {
  merchant: { id: string; name: string; slug: string };
  application: { id: string; name: string; environment: string };
  api_key: { id: string; name: string; last4: string };
};

const API_KEY_STORAGE = "ithute-pay-portal-test-key";

function prettyLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function PartnerTestingPortal() {
  const [apiKey, setApiKey] = useState("");
  const [context, setContext] = useState<PortalContext | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [product, setProduct] = useState("c2b");
  const [scenario, setScenario] = useState("success");
  const [amount, setAmount] = useState("25.00");
  const [currency, setCurrency] = useState("LSL");
  const [voucherCode, setVoucherCode] = useState("");
  const [result, setResult] = useState<any>(null);
  const [connecting, setConnecting] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const service = catalog?.services?.[product];
  const scenarioEntries = useMemo(() => Object.entries(service?.cases ?? {}), [service]);

  useEffect(() => {
    const stored = window.sessionStorage.getItem(API_KEY_STORAGE) || "";
    if (stored) setApiKey(stored);
  }, []);

  useEffect(() => {
    if (!service) return;
    const first = Object.keys(service.cases)[0];
    if (first && !(scenario in service.cases)) setScenario(first);
  }, [service, scenario]);

  async function authorizedFetch(path: string, init?: RequestInit, keyOverride?: string) {
    const key = (keyOverride ?? apiKey).trim();
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${key}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : "The request could not be completed.";
      throw new Error(detail);
    }
    return payload;
  }

  async function connect(event?: FormEvent) {
    event?.preventDefault();
    setConnecting(true);
    setError("");
    setResult(null);
    try {
      const key = apiKey.trim();
      if (!key.startsWith("ipb_test_")) throw new Error("Use an Ithute Pay sandbox/test API key beginning with ipb_test_.");
      const [nextContext, nextCatalog] = await Promise.all([
        authorizedFetch("/portal/context", undefined, key),
        authorizedFetch("/portal/testing/catalog", undefined, key),
      ]);
      window.sessionStorage.setItem(API_KEY_STORAGE, key);
      setContext(nextContext);
      setCatalog(nextCatalog);
      const firstProduct = Object.keys(nextCatalog.services || {})[0];
      if (firstProduct) {
        setProduct(firstProduct);
        const firstScenario = Object.keys(nextCatalog.services[firstProduct]?.cases || {})[0];
        if (firstScenario) setScenario(firstScenario);
      }
    } catch (connectError) {
      setContext(null);
      setCatalog(null);
      setError(connectError instanceof Error ? connectError.message : "Unable to connect to the testing portal.");
    } finally {
      setConnecting(false);
    }
  }

  function disconnect() {
    window.sessionStorage.removeItem(API_KEY_STORAGE);
    setApiKey("");
    setContext(null);
    setCatalog(null);
    setResult(null);
    setError("");
  }

  async function runTest() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const payload = await authorizedFetch("/portal/testing/mpesa/run", {
        method: "POST",
        body: JSON.stringify({
          product,
          scenario,
          amount,
          currency: currency.toUpperCase(),
          voucher_code: voucherCode || undefined,
          commit: true,
        }),
      });
      setResult(payload);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "The sandbox test failed to run.");
    } finally {
      setRunning(false);
    }
  }

  const selectedCase = service?.cases?.[scenario];

  return (
    <main className="min-h-screen bg-[#f4f8fb] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 lg:px-8">
          <div className="flex items-center gap-4">
            <img src="/brand/ithute-pay-bridge-horizontal.svg" alt="Ithute Pay" className="h-10 w-auto" />
            <div className="hidden border-l border-slate-200 pl-4 sm:block">
              <p className="text-xs font-black uppercase tracking-[.18em] text-[#116fbb]">Partner Test Portal</p>
              <p className="text-xs text-slate-500">Sandbox product validation for integration consumers</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="border-blue-200 bg-blue-50 text-blue-700">Sandbox only</Badge>
            {context && <Button variant="secondary" size="sm" onClick={disconnect}><RotateCcw className="h-4 w-4" />Disconnect</Button>}
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-5 py-8 lg:px-8">
        <div className="mb-7 grid gap-5 lg:grid-cols-[1.4fr_.6fr]">
          <div>
            <p className="text-xs font-black uppercase tracking-[.22em] text-[#116fbb]">portal.pay.ithute.co.ls</p>
            <h1 className="mt-3 max-w-4xl text-3xl font-black tracking-tight text-[#082b4d] sm:text-4xl">Test Ithute Pay exactly as a product consumer would.</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">Use a sandbox application key to exercise provider-facing capabilities without entering the super-admin dashboard. The portal exposes M-Pesa C2B, B2C, B2B, transaction queries, reversals, update/authorization flows and direct-debit scenarios against the configured sandbox.</p>
          </div>
          <Card className="border-blue-100 bg-blue-50/60">
            <CardContent className="flex h-full items-center gap-4 p-5">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white text-[#116fbb] shadow-sm"><ShieldCheck className="h-6 w-6" /></div>
              <div><p className="font-black text-[#082b4d]">Consumer boundary</p><p className="mt-1 text-xs leading-5 text-slate-600">No provider credentials, platform configuration, merchant administration or super-admin controls are exposed here.</p></div>
            </CardContent>
          </Card>
        </div>

        {!context ? (
          <Card className="mx-auto max-w-2xl border-0 shadow-[0_24px_70px_rgba(6,43,77,.10)]">
            <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="h-5 w-5 text-[#116fbb]" />Connect a sandbox application</CardTitle></CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={connect}>
                <div><label className="mb-1.5 block text-sm font-bold text-slate-700">Sandbox API key</label><Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="ipb_test_…" autoComplete="off" required /></div>
                <p className="text-xs leading-5 text-slate-500">The key is kept only in this browser tab session and is sent to the public Ithute Pay API as a Bearer credential. Production <code>ipb_live_</code> keys are rejected by this portal.</p>
                {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
                <Button className="w-full" size="lg" disabled={connecting}>{connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" />}{connecting ? "Connecting…" : "Open testing workspace"}</Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <Card><CardContent className="p-5"><p className="text-xs font-black uppercase tracking-[.16em] text-slate-400">Merchant</p><p className="mt-2 text-lg font-black text-[#082b4d]">{context.merchant.name}</p><p className="text-xs text-slate-500">{context.merchant.slug}</p></CardContent></Card>
              <Card><CardContent className="p-5"><p className="text-xs font-black uppercase tracking-[.16em] text-slate-400">Application</p><p className="mt-2 text-lg font-black text-[#082b4d]">{context.application.name}</p><p className="text-xs text-slate-500">Environment: {context.application.environment}</p></CardContent></Card>
              <Card><CardContent className="p-5"><p className="text-xs font-black uppercase tracking-[.16em] text-slate-400">Provider status</p><p className="mt-2 flex items-center gap-2 text-lg font-black text-[#082b4d]"><Activity className="h-5 w-5" />M-Pesa Sandbox</p><p className={`text-xs ${catalog?.ready ? "text-green-600" : "text-amber-600"}`}>{catalog?.ready ? "Ready for provider tests" : "Sandbox configuration needs attention"}</p></CardContent></Card>
            </div>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><TestTube2 className="h-5 w-5 text-[#116fbb]" />Choose a product capability</CardTitle></CardHeader>
              <CardContent className="space-y-5">
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {Object.entries(catalog?.services ?? {}).map(([id, item]) => (
                    <button key={id} type="button" onClick={() => setProduct(id)} className={`min-w-[170px] rounded-xl border px-4 py-3 text-left transition ${product === id ? "border-[#116fbb] bg-[#116fbb] text-white" : "border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50"}`}>
                      <span className="block text-sm font-black">{item.label}</span>
                      <span className={`mt-1 block text-[11px] ${product === id ? "text-blue-100" : "text-slate-500"}`}>{item.capability || prettyLabel(id)} · {Object.keys(item.cases).length} scenarios</span>
                    </button>
                  ))}
                </div>

                <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
                  <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
                    <div><label className="mb-1.5 block text-xs font-black uppercase tracking-[.14em] text-slate-500">Scenario</label><select className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm" value={scenario} onChange={(event) => setScenario(event.target.value)}>{scenarioEntries.map(([id, item]) => <option key={id} value={id}>{prettyLabel(id)} — {item.expected || "Provider scenario"}</option>)}</select></div>
                    <div className="grid grid-cols-2 gap-3"><div><label className="mb-1.5 block text-xs font-black uppercase tracking-[.14em] text-slate-500">Amount</label><Input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" /></div><div><label className="mb-1.5 block text-xs font-black uppercase tracking-[.14em] text-slate-500">Currency</label><Input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} /></div></div>
                    {service?.requires_voucher_code && <div><label className="mb-1.5 block text-xs font-black uppercase tracking-[.14em] text-slate-500">Voucher code</label><Input value={voucherCode} onChange={(event) => setVoucherCode(event.target.value)} placeholder="Voucher from multi-stage C2B" /></div>}
                    <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-xs leading-5 text-blue-800"><strong>Provider fixture:</strong> {service?.input_field || "Provider input"} = <code>{selectedCase?.value || "generated"}</code><br /><strong>Expected:</strong> {selectedCase?.expected || "Provider-defined response"}</div>
                    <Button className="w-full" size="lg" onClick={runTest} disabled={running || !catalog?.ready}>{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{running ? "Running provider test…" : `Run ${service?.label || "test"}`}</Button>
                  </div>

                  <div className="min-h-[330px] rounded-2xl border border-slate-200 bg-[#081727] p-5 text-slate-100">
                    <div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-black uppercase tracking-[.16em] text-slate-400">Test result</p><p className="mt-1 text-sm text-slate-300">Request and provider outcome</p></div>{result && <Badge className={result.passed ? "border-green-500/30 bg-green-500/10 text-green-300" : "border-red-500/30 bg-red-500/10 text-red-300"}>{result.passed ? "Passed" : "Failed"}</Badge>}</div>
                    {result ? <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">{JSON.stringify(result, null, 2)}</pre> : <div className="grid min-h-[230px] place-items-center text-center text-sm text-slate-500"><div><TestTube2 className="mx-auto mb-3 h-8 w-8" /><p>Run a sandbox scenario to see the exact gateway and provider result here.</p></div></div>}
                  </div>
                </div>
                {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
              </CardContent>
            </Card>
          </div>
        )}
      </section>
    </main>
  );
}
