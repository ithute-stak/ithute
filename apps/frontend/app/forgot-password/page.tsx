"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, KeyRound, Mail, ShieldCheck } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [isHttps, setIsHttps] = useState<boolean | null>(null);

  useEffect(() => {
    setIsHttps(window.location.protocol === "https:");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/auth/password-reset/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (response.status === 400) {
        const body = await response.json().catch(() => ({}));
        if (String(body.detail || "").toLowerCase().includes("https")) {
          setError("Password recovery is disabled on the temporary HTTP bootstrap address. Use the HTTPS platform domain once it is activated.");
          return;
        }
      }
      if (response.status === 429) {
        setError("Too many recovery requests. Please wait before trying again.");
        return;
      }
      if (response.status === 503) {
        setError("Account recovery email is temporarily unavailable. Please try again later.");
        return;
      }
      if (!response.ok) {
        setError("We could not start account recovery. Please try again.");
        return;
      }
      setSubmitted(true);
    } catch {
      setError("The recovery service is temporarily unreachable. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#071c18] px-5 py-10 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(72,154,136,.25),transparent_28%),radial-gradient(circle_at_82%_18%,rgba(216,197,106,.18),transparent_25%),linear-gradient(135deg,#071c18,#0d332d)]" />
      <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.035)_1px,transparent_1px)] [background-size:52px_52px]" />

      <div className="relative mx-auto flex min-h-[calc(100vh-5rem)] max-w-[1120px] items-center justify-center">
        <section className="w-full max-w-[520px] rounded-[32px] border border-white/15 bg-white/[.98] p-6 text-[#1f3329] shadow-[0_40px_120px_rgba(0,0,0,.38)] sm:p-9">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#123a38] text-sm font-black text-[#f0dd80]">MD</div>
              <div><p className="text-sm font-black">Mailbox DNS</p><p className="text-[9px] font-black uppercase tracking-[.16em] text-[#89958e]">Account recovery</p></div>
            </div>
            <ShieldCheck size={21} className="text-[#285b55]" />
          </div>

          {isHttps === false ? <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[10px] leading-5 text-amber-900"><span className="font-black">HTTPS required for recovery.</span> The current raw-IP bootstrap page can still be used for temporary sign-in, but password reset links are intentionally disabled until the secure platform domain is active.</div> : null}

          {!submitted ? (
            <>
              <div className="mt-8 grid h-12 w-12 place-items-center rounded-2xl bg-[#eef4f1] text-[#285b55]"><KeyRound size={20} /></div>
              <h1 className="mt-4 text-[32px] font-black tracking-[-.045em]">Reset your password</h1>
              <p className="mt-2 text-[12px] leading-5 text-[#748179]">Enter the account email. If it matches an active account, we’ll send a one-time recovery link that expires in 30 minutes.</p>

              <form onSubmit={submit} className="mt-7 space-y-4">
                <div>
                  <label htmlFor="email" className="label">Email address</label>
                  <div className="relative">
                    <Mail size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#85928a]" />
                    <input id="email" className="input min-h-[48px] pl-11" type="email" required autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.co.ls" />
                  </div>
                </div>
                {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[11px] font-semibold leading-5 text-red-700">{error}</div> : null}
                <button type="submit" disabled={loading || isHttps === false} className="flex min-h-[50px] w-full items-center justify-center gap-2 rounded-xl bg-[#123a38] px-4 text-[12px] font-black text-white shadow-[0_14px_34px_rgba(18,58,56,.20)] transition hover:-translate-y-0.5 hover:bg-[#285b55] disabled:cursor-not-allowed disabled:opacity-50">
                  {loading ? "Preparing recovery…" : "Send recovery link"}<ArrowRight size={16} />
                </button>
              </form>
            </>
          ) : (
            <div className="py-8 text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><Mail size={22} /></div>
              <h1 className="mt-5 text-[30px] font-black tracking-[-.04em]">Check your inbox</h1>
              <p className="mx-auto mt-3 max-w-[390px] text-[12px] leading-6 text-[#748179]">If an active account matches <span className="font-black text-[#35463c]">{email}</span>, a one-time password recovery link has been sent. This response is deliberately the same for registered and unregistered addresses.</p>
            </div>
          )}

          <div className="mt-6 border-t border-[#e5eae7] pt-5">
            <Link href="/login" className="inline-flex items-center gap-2 text-[11px] font-black text-[#285b55] hover:underline"><ArrowLeft size={14} /> Back to sign in</Link>
            <p className="mt-4 text-[9px] leading-4 text-[#98a39d]">Recovery links are single-use. A successful password reset revokes every existing signed-in session for the account.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
