"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";

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
    <main className="min-h-screen bg-[#f4f7f6] text-[#17362e]">
      <div className="grid min-h-screen lg:grid-cols-[1.05fr_.95fr]">
        <section className="relative hidden overflow-hidden bg-[linear-gradient(145deg,#073a30_0%,#0a5f4b_56%,#0b755c_100%)] px-10 py-10 text-white lg:flex lg:flex-col lg:justify-between xl:px-16 xl:py-14">
          <div className="absolute -left-36 top-[24%] h-[420px] w-[420px] rounded-full border border-white/10" />
          <div className="absolute -right-44 -top-40 h-[520px] w-[520px] rounded-full border border-amber-100/15" />
          <div className="absolute bottom-[9%] right-[7%] h-24 w-24 opacity-25 [background-image:radial-gradient(circle,#f0d674_1.4px,transparent_1.5px)] [background-size:15px_15px]" />

          <div className="relative z-10 flex items-center gap-3.5">
            <div className="grid h-14 w-14 place-items-center rounded-[18px] border border-white/15 bg-white/10 shadow-[0_18px_40px_rgba(0,0,0,.16)] backdrop-blur">
              <Mail size={25} />
            </div>
            <div>
              <p className="text-[24px] font-black leading-none tracking-[-.045em]">Ithute Mail</p>
              <p className="mt-1.5 text-[10px] font-black uppercase tracking-[.23em] text-emerald-100/75">Webmail</p>
            </div>
          </div>

          <div className="relative z-10 max-w-[590px]">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-[.18em] text-emerald-50 backdrop-blur">
              <ShieldCheck size={14} />
              Secure account recovery
            </div>

            <h1 className="mt-7 text-[50px] font-black leading-[1.02] tracking-[-.055em] xl:text-[58px]">
              Recover access.
              <span className="mt-2 block text-[#efd76d]">Keep your account protected.</span>
            </h1>

            <p className="mt-6 max-w-[540px] text-[15px] leading-7 text-emerald-50/78">
              We use one-time, time-limited recovery links and privacy-safe responses so account recovery does not reveal whether an email address exists.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {[
                ["One-time link", "Recovery links are single-use and expire after 30 minutes."],
                ["Privacy-safe response", "Registered and unregistered addresses receive the same confirmation message."],
                ["Session revocation", "A successful password reset signs out existing local sessions."],
                ["Central Auth aware", "Accounts protected by Central Authentication remain on Central Authentication."],
              ].map(([title, detail]) => (
                <div key={title} className="rounded-2xl border border-white/12 bg-white/[.08] p-4 backdrop-blur">
                  <p className="text-[12px] font-black text-white">{title}</p>
                  <p className="mt-1 text-[10px] leading-5 text-emerald-50/65">{detail}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="relative z-10 flex items-center gap-2 text-[10px] font-semibold text-emerald-100/65">
            <ShieldCheck size={14} />
            Recovery email sent from auth@ithute.co.ls
          </div>
        </section>

        <section className="relative flex min-h-screen items-center justify-center px-4 py-8 sm:px-8 lg:px-10 xl:px-16">
          <div className="absolute inset-x-0 top-0 h-32 bg-[linear-gradient(180deg,rgba(8,115,87,.055),transparent)] lg:hidden" />

          <div className="relative w-full max-w-[560px]">
            <div className="mb-7 flex items-center justify-between lg:hidden">
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#0b5d49] text-white shadow-sm">
                  <Mail size={20} />
                </div>
                <div>
                  <p className="text-[19px] font-black tracking-[-.04em] text-[#123b31]">Ithute Mail</p>
                  <p className="text-[9px] font-black uppercase tracking-[.2em] text-[#84968e]">Webmail</p>
                </div>
              </div>
              <ShieldCheck className="text-[#0b755c]" size={21} />
            </div>

            <div className="rounded-[30px] border border-[#dbe6e1] bg-white p-5 shadow-[0_26px_80px_rgba(16,54,43,.11)] sm:p-8 xl:p-10">
              {isHttps === false ? (
                <div className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-amber-900">
                  <div className="flex items-start gap-3">
                    <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                    <div>
                      <p className="text-[11px] font-black">HTTPS required for recovery</p>
                      <p className="mt-1 text-[10px] leading-5">
                        The temporary HTTP bootstrap address may be used for temporary sign-in, but password recovery remains disabled until the secure platform domain is active.
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}

              {!submitted ? (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[.19em] text-[#0a765d]">Account recovery</p>
                      <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#14372f] sm:text-[40px]">
                        Reset your password
                      </h1>
                      <p className="mt-3 max-w-[470px] text-[13px] leading-6 text-[#6e8178]">
                        Enter the email address connected to your Ithute account. If eligible, we’ll send a single-use recovery link that expires after 30 minutes.
                      </p>
                    </div>
                    <div className="hidden h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#eef7f3] text-[#176c56] sm:grid">
                      <KeyRound size={19} />
                    </div>
                  </div>

                  <form onSubmit={submit} className="mt-7 space-y-5">
                    <div>
                      <label htmlFor="email" className="mb-2 block text-[11px] font-black text-[#24483d]">
                        Email address
                      </label>
                      <div className="relative">
                        <Mail size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#678078]" />
                        <input
                          id="email"
                          className="min-h-[54px] w-full rounded-2xl border border-[#cfddd7] bg-[#fbfdfc] px-12 text-[13px] font-semibold text-[#203f35] outline-none transition placeholder:text-[#98a8a1] focus:border-[#27836a] focus:bg-white focus:ring-4 focus:ring-[#27836a]/10"
                          type="email"
                          required
                          autoComplete="email"
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          placeholder="you@company.co.ls"
                        />
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[#d8e7e0] bg-[#f0f7f4] p-4">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[#176c56] shadow-sm">
                          <ShieldCheck size={17} />
                        </div>
                        <div>
                          <p className="text-[11px] font-black text-[#25483e]">Privacy-safe recovery</p>
                          <p className="mt-1 text-[10px] leading-5 text-[#71837b]">
                            For security, the result will not confirm whether the email address is registered. Never share the recovery link with anyone.
                          </p>
                        </div>
                      </div>
                    </div>

                    {error ? (
                      <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[11px] font-semibold leading-5 text-red-700">
                        {error}
                      </div>
                    ) : null}

                    <button
                      type="submit"
                      disabled={loading || isHttps === false}
                      className="flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-4 text-[13px] font-black text-white shadow-[0_16px_38px_rgba(10,101,79,.23)] transition hover:-translate-y-0.5 hover:shadow-[0_20px_42px_rgba(10,101,79,.28)] disabled:cursor-not-allowed disabled:opacity-55"
                    >
                      {loading ? <Loader2 size={17} className="animate-spin" /> : <Mail size={17} />}
                      {loading ? "Preparing recovery…" : "Send recovery link"}
                      {!loading ? <ArrowRight size={16} /> : null}
                    </button>
                  </form>
                </>
              ) : (
                <div className="py-4 text-center sm:py-8">
                  <div className="mx-auto grid h-17 w-17 place-items-center rounded-[22px] bg-emerald-50 text-emerald-700">
                    <CheckCircle2 size={30} />
                  </div>
                  <p className="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-[#6f8c81]">Recovery request sent</p>
                  <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#153a31] sm:text-[39px]">
                    Check your inbox
                  </h1>
                  <p className="mx-auto mt-4 max-w-[420px] text-[13px] leading-6 text-[#6e8178]">
                    If an eligible account matches <span className="font-black text-[#35463c]">{email}</span>, a one-time recovery link has been sent from <strong>auth@ithute.co.ls</strong>.
                  </p>
                  <p className="mx-auto mt-3 max-w-[420px] text-[10px] leading-5 text-[#8a9891]">
                    This confirmation is deliberately identical for registered and unregistered email addresses.
                  </p>
                  <Link
                    href="/login"
                    className="mt-8 inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-6 text-[13px] font-black text-white shadow-[0_16px_36px_rgba(10,101,79,.22)] transition hover:-translate-y-0.5"
                  >
                    <ArrowLeft size={16} />
                    Back to sign in
                  </Link>
                </div>
              )}

              {!submitted ? (
                <div className="mt-6 border-t border-[#e2ebe7] pt-5">
                  <Link href="/login" className="inline-flex items-center gap-2 text-[11px] font-black text-[#285b55] transition hover:text-[#0a6a53]">
                    <ArrowLeft size={14} />
                    Back to sign in
                  </Link>
                </div>
              ) : null}
            </div>

            <p className="mt-5 text-center text-[10px] leading-5 text-[#84958e]">
              Recovery links are single-use, expire after 30 minutes, and successful resets revoke existing local sessions.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
