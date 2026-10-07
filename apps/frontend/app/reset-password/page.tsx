"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const fragment = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(fragment);
    const value = params.get("token") || "";
    setToken(value);
    if (value) window.history.replaceState({}, "", "/reset-password");
  }, []);

  const requirements = useMemo(
    () => [
      { label: "At least 12 characters", met: password.length >= 12 },
      { label: "Passwords match", met: password.length > 0 && password === confirmPassword },
    ],
    [password, confirmPassword],
  );

  const strengthLabel = useMemo(() => {
    if (!password) return "Waiting for your new password";
    if (password.length < 12) return "Needs more characters";
    if (password.length >= 16) return "Strong password length";
    return "Good password length";
  }, [password]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!token) {
      setError("This recovery link is missing its one-time token. Request a new password reset link.");
      return;
    }
    if (password.length < 12) {
      setError("Use at least 12 characters for your new password.");
      return;
    }
    if (password !== confirmPassword) {
      setError("The two password entries do not match.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API}/auth/password-reset/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token, new_password: password }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = String(body.detail || "").toLowerCase();

        if (detail.includes("invalid") || detail.includes("expired")) {
          setError("This recovery link is invalid, expired or has already been used. Request a new one.");
        } else if (detail.includes("not just been using")) {
          setError("Choose a new password that is different from your current password.");
        } else if (response.status === 400 && detail.includes("https")) {
          setError("This password can only be reset over the secure HTTPS platform address.");
        } else {
          setError("We could not reset the password. Please request a new recovery link and try again.");
        }
        return;
      }

      setComplete(true);
      setPassword("");
      setConfirmPassword("");
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
              Reset your password.
              <span className="mt-2 block text-[#efd76d]">Keep control of your account.</span>
            </h1>
            <p className="mt-6 max-w-[540px] text-[15px] leading-7 text-emerald-50/78">
              Your recovery link is single-use and time-limited. Create a new password here, then sign back in on devices you trust.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {[
                ["One-time recovery", "The reset token is removed from the address bar after this page opens."],
                ["Session protection", "Existing local sessions are revoked after a successful password change."],
                ["Private by design", "Your new password is submitted only to the secure recovery endpoint."],
                ["Back to work quickly", "Return directly to sign-in when the reset is complete."],
              ].map(([title, detail]) => (
                <div key={title} className="rounded-2xl border border-white/12 bg-white/[.08] p-4 backdrop-blur">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-white/10 text-[#efd76d]">
                      <Check size={15} strokeWidth={3} />
                    </div>
                    <div>
                      <p className="text-[12px] font-black text-white">{title}</p>
                      <p className="mt-1 text-[10px] leading-5 text-emerald-50/65">{detail}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative z-10 flex items-center gap-2 text-[10px] font-semibold text-emerald-100/65">
            <ShieldCheck size={14} />
            Ithute secure recovery service
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
              {complete ? (
                <div className="py-4 text-center sm:py-8">
                  <div className="mx-auto grid h-17 w-17 place-items-center rounded-[22px] bg-emerald-50 text-emerald-700">
                    <CheckCircle2 size={30} />
                  </div>
                  <p className="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-[#6f8c81]">Recovery complete</p>
                  <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#153a31] sm:text-[39px]">
                    Password updated
                  </h1>
                  <p className="mx-auto mt-4 max-w-[420px] text-[13px] leading-6 text-[#6e8178]">
                    Your password has been changed and your existing local sessions were revoked. Sign in again only on devices you trust.
                  </p>
                  <Link
                    href="/login"
                    className="mt-8 inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-6 text-[13px] font-black text-white shadow-[0_16px_36px_rgba(10,101,79,.22)] transition hover:-translate-y-0.5 hover:shadow-[0_20px_42px_rgba(10,101,79,.28)]"
                  >
                    <KeyRound size={17} />
                    Sign in with new password
                    <ArrowRight size={16} />
                  </Link>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[.19em] text-[#0a765d]">Secure password reset</p>
                      <h1 className="mt-2 text-[34px] font-black tracking-[-.05em] text-[#14372f] sm:text-[40px]">
                        Choose a new password
                      </h1>
                      <p className="mt-3 max-w-[470px] text-[13px] leading-6 text-[#6e8178]">
                        Create a strong, unique password for your Ithute account. This verification link works once and expires after 30 minutes.
                      </p>
                    </div>
                    <div className="hidden h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#eef7f3] text-[#176c56] sm:grid">
                      <Sparkles size={19} />
                    </div>
                  </div>

                  {!token ? (
                    <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-amber-800">
                      <div className="flex items-start gap-3">
                        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                        <div>
                          <p className="text-[11px] font-black">Recovery link required</p>
                          <p className="mt-1 text-[10px] leading-5">
                            This page does not contain a valid one-time reset token. Request a fresh recovery email before continuing.
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  <form onSubmit={submit} className="mt-7 space-y-5">
                    <div>
                      <label htmlFor="new_password" className="mb-2 block text-[11px] font-black text-[#24483d]">
                        New password
                      </label>
                      <div className="relative">
                        <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#678078]" />
                        <input
                          id="new_password"
                          className="min-h-[54px] w-full rounded-2xl border border-[#cfddd7] bg-[#fbfdfc] px-12 pr-14 text-[13px] font-semibold text-[#203f35] outline-none transition placeholder:text-[#98a8a1] focus:border-[#27836a] focus:bg-white focus:ring-4 focus:ring-[#27836a]/10"
                          type={showPassword ? "text" : "password"}
                          required
                          minLength={12}
                          maxLength={256}
                          autoComplete="new-password"
                          value={password}
                          onChange={(event) => setPassword(event.target.value)}
                          placeholder="At least 12 characters"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((value) => !value)}
                          className="absolute right-3 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-xl text-[#6e8279] transition hover:bg-[#eef5f2] hover:text-[#285b55]"
                          aria-label={showPassword ? "Hide password" : "Show password"}
                        >
                          {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                        </button>
                      </div>
                    </div>

                    <div>
                      <label htmlFor="confirm_password" className="mb-2 block text-[11px] font-black text-[#24483d]">
                        Confirm new password
                      </label>
                      <div className="relative">
                        <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#678078]" />
                        <input
                          id="confirm_password"
                          className="min-h-[54px] w-full rounded-2xl border border-[#cfddd7] bg-[#fbfdfc] px-12 pr-14 text-[13px] font-semibold text-[#203f35] outline-none transition placeholder:text-[#98a8a1] focus:border-[#27836a] focus:bg-white focus:ring-4 focus:ring-[#27836a]/10"
                          type={showConfirmPassword ? "text" : "password"}
                          required
                          minLength={12}
                          maxLength={256}
                          autoComplete="new-password"
                          value={confirmPassword}
                          onChange={(event) => setConfirmPassword(event.target.value)}
                          placeholder="Repeat the new password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowConfirmPassword((value) => !value)}
                          className="absolute right-3 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-xl text-[#6e8279] transition hover:bg-[#eef5f2] hover:text-[#285b55]"
                          aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                        >
                          {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[#d8e7e0] bg-[#f0f7f4] p-4">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[#176c56] shadow-sm">
                          <ShieldCheck size={17} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-[11px] font-black text-[#25483e]">Password check</p>
                            <span className="text-[9px] font-black uppercase tracking-[.12em] text-[#698078]">{strengthLabel}</span>
                          </div>
                          <p className="mt-1 text-[10px] leading-5 text-[#71837b]">
                            Use a password unique to Ithute. Do not reuse a mailbox or banking password.
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {requirements.map((item) => (
                              <span
                                key={item.label}
                                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-black ${item.met ? "border-emerald-200 bg-white text-emerald-700" : "border-[#dce7e2] bg-white/70 text-[#7f9088]"}`}
                              >
                                <Check size={11} strokeWidth={3} />
                                {item.label}
                              </span>
                            ))}
                          </div>
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
                      disabled={loading || !token}
                      className="flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-4 text-[13px] font-black text-white shadow-[0_16px_38px_rgba(10,101,79,.23)] transition hover:-translate-y-0.5 hover:shadow-[0_20px_42px_rgba(10,101,79,.28)] disabled:cursor-not-allowed disabled:opacity-55"
                    >
                      {loading ? <Loader2 size={17} className="animate-spin" /> : <ShieldCheck size={17} />}
                      {loading ? "Securing account…" : "Update password"}
                      {!loading ? <ArrowRight size={16} /> : null}
                    </button>
                  </form>

                  <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#e2ebe7] pt-5">
                    <Link href="/login" className="inline-flex items-center gap-2 text-[11px] font-black text-[#285b55] transition hover:text-[#0a6a53]">
                      <ArrowLeft size={14} />
                      Back to sign in
                    </Link>
                    <Link href="/forgot-password" className="text-[11px] font-black text-[#0a765d] transition hover:text-[#075844]">
                      Request a new link
                    </Link>
                  </div>
                </>
              )}
            </div>

            <p className="mt-5 text-center text-[10px] leading-5 text-[#84958e]">
              Ithute Mail secure recovery • Never share your reset link or one-time recovery token.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
