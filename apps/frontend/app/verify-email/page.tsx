"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type VerificationState = "checking" | "success" | "error";

export default function VerifyEmailPage() {
  const [status, setStatus] = useState<VerificationState>("checking");
  const [message, setMessage] = useState("Verifying your email address…");

  useEffect(() => {
    let active = true;

    void (async () => {
      const token = new URLSearchParams(window.location.search).get("token");

      if (!token) {
        if (active) {
          setStatus("error");
          setMessage("This verification link is missing its one-time token.");
        }
        return;
      }

      window.history.replaceState({}, "", "/verify-email");

      try {
        const response = await fetch(`${API}/public/email-verification/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        const body = await response.json().catch(() => ({}));

        if (!active) return;

        if (response.ok) {
          setStatus("success");
          setMessage("Your email address has been verified successfully.");
          return;
        }

        setStatus("error");
        setMessage(String(body.detail || "This verification link is invalid, expired or has already been used."));
      } catch {
        if (active) {
          setStatus("error");
          setMessage("The verification service is temporarily unreachable. Please try again from the verification email.");
        }
      }
    })();

    return () => {
      active = false;
    };
  }, []);

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
              Verified identity
            </div>
            <h1 className="mt-7 text-[50px] font-black leading-[1.02] tracking-[-.055em] xl:text-[58px]">
              Verify your email.
              <span className="mt-2 block text-[#efd76d]">Secure your Ithute identity.</span>
            </h1>
            <p className="mt-6 max-w-[540px] text-[15px] leading-7 text-emerald-50/78">
              Email verification confirms that you control the address attached to your Ithute account before trusted account actions continue.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {[
                ["One-time verification", "Verification links are intended for a single account action."],
                ["Token removed", "The token is removed from the browser address after this page opens."],
                ["Account protection", "Verification strengthens recovery and trusted-account workflows."],
                ["Clear next step", "Successful verification returns you directly to sign-in."],
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
            Ithute secure identity verification
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
              {status === "checking" ? (
                <div className="py-6 text-center sm:py-10">
                  <div className="mx-auto grid h-17 w-17 place-items-center rounded-[22px] bg-[#eef7f3] text-[#0a765d]">
                    <Loader2 size={30} className="animate-spin" />
                  </div>
                  <p className="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-[#6f8c81]">Verifying email</p>
                  <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#153a31] sm:text-[39px]">
                    Checking your link
                  </h1>
                  <p className="mx-auto mt-4 max-w-[420px] text-[13px] leading-6 text-[#6e8178]">
                    We’re confirming the one-time verification token securely.
                  </p>
                </div>
              ) : status === "success" ? (
                <div className="py-4 text-center sm:py-8">
                  <div className="mx-auto grid h-17 w-17 place-items-center rounded-[22px] bg-emerald-50 text-emerald-700">
                    <CheckCircle2 size={30} />
                  </div>
                  <p className="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-[#6f8c81]">Verification complete</p>
                  <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#153a31] sm:text-[39px]">
                    Email verified
                  </h1>
                  <p className="mx-auto mt-4 max-w-[420px] text-[13px] leading-6 text-[#6e8178]">{message}</p>

                  <Link
                    href="/login"
                    className="mt-8 inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-6 text-[13px] font-black text-white shadow-[0_16px_36px_rgba(10,101,79,.22)] transition hover:-translate-y-0.5"
                  >
                    Go to sign in
                    <ArrowRight size={16} />
                  </Link>
                </div>
              ) : (
                <div className="py-4 text-center sm:py-8">
                  <div className="mx-auto grid h-17 w-17 place-items-center rounded-[22px] bg-amber-50 text-amber-700">
                    <AlertTriangle size={30} />
                  </div>
                  <p className="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-[#9a7a25]">Verification incomplete</p>
                  <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#153a31] sm:text-[39px]">
                    Link could not be verified
                  </h1>
                  <p className="mx-auto mt-4 max-w-[420px] text-[13px] leading-6 text-[#6e8178]">{message}</p>

                  <div className="mt-8 grid gap-3 sm:grid-cols-2">
                    <Link
                      href="/login"
                      className="inline-flex min-h-[50px] items-center justify-center gap-2 rounded-2xl border border-[#d7e4de] bg-white px-5 text-[12px] font-black text-[#285b55] transition hover:bg-[#f4f8f6]"
                    >
                      <ArrowLeft size={15} />
                      Back to sign in
                    </Link>
                    <Link
                      href="/forgot-password"
                      className="inline-flex min-h-[50px] items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-5 text-[12px] font-black text-white shadow-[0_14px_32px_rgba(10,101,79,.18)]"
                    >
                      Account recovery
                      <ArrowRight size={15} />
                    </Link>
                  </div>
                </div>
              )}
            </div>

            <p className="mt-5 text-center text-[10px] leading-5 text-[#84958e]">
              Only use verification links from Ithute communications you expected to receive.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
