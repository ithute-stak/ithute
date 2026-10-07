"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const fragment = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
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
    <main className="relative min-h-screen overflow-hidden bg-[#082d26] px-4 py-7 text-white sm:px-6 sm:py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_17%_14%,rgba(69,162,132,.30),transparent_30%),radial-gradient(circle_at_85%_11%,rgba(240,214,116,.30),transparent_27%),radial-gradient(circle_at_58%_90%,rgba(45,115,87,.23),transparent_34%),linear-gradient(135deg,#072820_0%,#0b493c_48%,#123a30_100%)]" />
      <div className="absolute -left-64 top-[36%] h-[520px] w-[520px] rounded-full border border-emerald-100/15" />
      <div className="absolute -right-40 -top-72 h-[560px] w-[560px] rounded-full border border-amber-100/20" />
      <div className="absolute left-[7%] top-[18%] hidden h-20 w-20 opacity-30 [background-image:radial-gradient(circle,#70c6a8_1.4px,transparent_1.5px)] [background-size:15px_15px] lg:block" />
      <div className="absolute bottom-[11%] right-[7%] hidden h-20 w-20 opacity-25 [background-image:radial-gradient(circle,#e6d274_1.4px,transparent_1.5px)] [background-size:15px_15px] lg:block" />

      <div className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-[1180px] items-center justify-center">
        <section className="w-full max-w-[570px] rounded-[34px] border border-white/60 bg-white/[.965] p-6 text-[#17362e] shadow-[0_38px_110px_rgba(1,19,15,.36)] backdrop-blur-xl sm:p-10">
          <div className="flex items-start justify-between gap-5">
            <div className="flex items-center gap-3.5">
              <div className="relative grid h-14 w-14 place-items-center rounded-[18px] bg-[linear-gradient(145deg,#0b755c,#084b3d)] text-white shadow-[0_12px_30px_rgba(9,91,71,.20)]">
                <Mail size={25} strokeWidth={2.2} />
                <span className="absolute -right-1 -top-1 h-4 w-4 rounded-full border-[3px] border-white bg-[#e2b72d]" />
              </div>
              <div>
                <p className="text-[24px] font-black leading-none tracking-[-.045em] text-[#123b31]">iMail</p>
                <p className="mt-1.5 text-[9px] font-black uppercase tracking-[.23em] text-[#83928b]">by Ithute</p>
                <p className="mt-2 text-[9px] font-black uppercase tracking-[.18em] text-[#4f6c62]">Secure password reset</p>
              </div>
            </div>
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf6f2] text-[#176c56]">
              <ShieldCheck size={20} />
            </div>
          </div>

          {complete ? (
            <div className="py-9 text-center">
              <div className="mx-auto grid h-16 w-16 place-items-center rounded-[20px] bg-emerald-50 text-emerald-700">
                <CheckCircle2 size={28} />
              </div>
              <h1 className="mt-6 text-[32px] font-black tracking-[-.045em] text-[#153a31]">Password updated</h1>
              <p className="mx-auto mt-3 max-w-[410px] text-[13px] leading-6 text-[#6e8178]">
                Your password has been changed and your existing local sessions were revoked. Sign in again only on devices you trust.
              </p>
              <Link
                href="/login"
                className="mt-8 inline-flex min-h-[50px] items-center justify-center gap-2 rounded-xl bg-[#0b5d49] px-7 text-[12px] font-black text-white shadow-[0_15px_34px_rgba(12,88,69,.20)] transition hover:-translate-y-0.5 hover:bg-[#087357]"
              >
                <KeyRound size={16} />
                Sign in with new password
              </Link>
            </div>
          ) : (
            <>
              <div className="mt-9">
                <h1 className="text-[34px] font-black tracking-[-.05em] text-[#14372f] sm:text-[38px]">Choose a new password</h1>
                <p className="mt-3 max-w-[470px] text-[13px] leading-6 text-[#6e8178]">
                  Create a strong, unique password for your Ithute account. This verification link works once and expires after 30 minutes.
                </p>
              </div>

              <form onSubmit={submit} className="mt-7 space-y-5">
                <div>
                  <label htmlFor="new_password" className="mb-2 block text-[11px] font-black text-[#24483d]">New password</label>
                  <div className="relative">
                    <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#678078]" />
                    <input
                      id="new_password"
                      className="min-h-[54px] w-full rounded-2xl border border-[#cfddd7] bg-white px-12 pr-14 text-[13px] font-semibold text-[#203f35] outline-none transition placeholder:text-[#98a8a1] focus:border-[#27836a] focus:ring-4 focus:ring-[#27836a]/10"
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
                  <label htmlFor="confirm_password" className="mb-2 block text-[11px] font-black text-[#24483d]">Confirm new password</label>
                  <div className="relative">
                    <LockKeyhole size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#678078]" />
                    <input
                      id="confirm_password"
                      className="min-h-[54px] w-full rounded-2xl border border-[#cfddd7] bg-white px-12 pr-14 text-[13px] font-semibold text-[#203f35] outline-none transition placeholder:text-[#98a8a1] focus:border-[#27836a] focus:ring-4 focus:ring-[#27836a]/10"
                      type={showPassword ? "text" : "password"}
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
                      onClick={() => setShowPassword((value) => !value)}
                      className="absolute right-3 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-xl text-[#6e8279] transition hover:bg-[#eef5f2] hover:text-[#285b55]"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-[#d8e7e0] bg-[#eef7f3] p-4">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[#176c56] shadow-sm">
                      <ShieldCheck size={17} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11px] font-black text-[#25483e]">Keep your account secure</p>
                      <p className="mt-1 text-[10px] leading-5 text-[#71837b]">
                        Use a password unique to Ithute and store it in a trusted password manager. Never reuse it for mailboxes or other services.
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
                  disabled={loading}
                  className="flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0a654f,#087357)] px-4 text-[13px] font-black text-white shadow-[0_16px_38px_rgba(10,101,79,.23)] transition hover:-translate-y-0.5 hover:shadow-[0_20px_42px_rgba(10,101,79,.28)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? "Securing account…" : "Update password"}
                  <ShieldCheck size={17} />
                </button>
              </form>
            </>
          )}

          {!complete ? (
            <div className="mt-6 border-t border-[#e2ebe7] pt-5">
              <Link href="/login" className="inline-flex items-center gap-2 text-[11px] font-black text-[#285b55] transition hover:text-[#0a6a53]">
                <ArrowLeft size={14} />
                Back to sign in
              </Link>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
