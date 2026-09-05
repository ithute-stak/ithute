"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, KeyRound, LockKeyhole, ShieldCheck } from "lucide-react";

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
    // The fragment never reaches the HTTP server. Remove it from browser
    // history immediately after capture so it cannot be recovered casually.
    if (value) window.history.replaceState({}, "", "/reset-password");
  }, []);

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
    <main className="relative min-h-screen overflow-hidden bg-[#071c18] px-5 py-10 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(72,154,136,.25),transparent_28%),radial-gradient(circle_at_82%_16%,rgba(216,197,106,.18),transparent_25%),linear-gradient(135deg,#071c18,#0d332d)]" />
      <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.035)_1px,transparent_1px)] [background-size:52px_52px]" />

      <div className="relative mx-auto flex min-h-[calc(100vh-5rem)] max-w-[1120px] items-center justify-center">
        <section className="w-full max-w-[540px] rounded-[32px] border border-white/15 bg-white/[.98] p-6 text-[#1f3329] shadow-[0_40px_120px_rgba(0,0,0,.38)] sm:p-9">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#123a38] text-sm font-black text-[#f0dd80]">MD</div>
              <div><p className="text-sm font-black">Mailbox DNS</p><p className="text-[9px] font-black uppercase tracking-[.16em] text-[#89958e]">Secure password reset</p></div>
            </div>
            <ShieldCheck size={21} className="text-[#285b55]" />
          </div>

          {complete ? (
            <div className="py-8 text-center">
              <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><CheckCircle2 size={26} /></div>
              <h1 className="mt-5 text-[30px] font-black tracking-[-.04em]">Password updated</h1>
              <p className="mx-auto mt-3 max-w-[410px] text-[12px] leading-6 text-[#748179]">Your password has been changed and all existing refresh sessions were revoked. Sign in again on devices you still trust.</p>
              <Link href="/login" className="mt-7 inline-flex min-h-[46px] items-center justify-center gap-2 rounded-xl bg-[#123a38] px-6 text-[11px] font-black text-white hover:bg-[#285b55]"><KeyRound size={15} /> Sign in with new password</Link>
            </div>
          ) : (
            <>
              <div className="mt-8 grid h-12 w-12 place-items-center rounded-2xl bg-[#eef4f1] text-[#285b55]"><LockKeyhole size={20} /></div>
              <h1 className="mt-4 text-[32px] font-black tracking-[-.045em]">Choose a new password</h1>
              <p className="mt-2 text-[12px] leading-5 text-[#748179]">Use a unique password of at least 12 characters. The recovery link works once and expires after 30 minutes.</p>

              <form onSubmit={submit} className="mt-7 space-y-4">
                <div>
                  <label htmlFor="new_password" className="label">New password</label>
                  <div className="relative">
                    <LockKeyhole size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#85928a]" />
                    <input id="new_password" className="input min-h-[48px] pl-11 pr-12" type={showPassword ? "text" : "password"} required minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 12 characters" />
                    <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-2.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-[#78867e] transition hover:bg-[#f0f4f1]" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                  </div>
                </div>
                <div>
                  <label htmlFor="confirm_password" className="label">Confirm new password</label>
                  <input id="confirm_password" className="input min-h-[48px]" type={showPassword ? "text" : "password"} required minLength={12} maxLength={256} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repeat the new password" />
                </div>

                <div className="rounded-xl border border-[#dde5e0] bg-[#f7faf8] px-4 py-3 text-[10px] leading-5 text-[#6e7d75]">
                  A good password is long, unique to Mailbox DNS and stored in a password manager. Never reuse the platform-owner password for mailboxes or other services.
                </div>
                {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[11px] font-semibold leading-5 text-red-700">{error}</div> : null}
                <button type="submit" disabled={loading} className="flex min-h-[50px] w-full items-center justify-center gap-2 rounded-xl bg-[#123a38] px-4 text-[12px] font-black text-white shadow-[0_14px_34px_rgba(18,58,56,.20)] transition hover:-translate-y-0.5 hover:bg-[#285b55] disabled:opacity-60">
                  {loading ? "Securing account…" : "Update password"}<ShieldCheck size={16} />
                </button>
              </form>
            </>
          )}

          {!complete ? <div className="mt-6 border-t border-[#e5eae7] pt-5"><Link href="/login" className="inline-flex items-center gap-2 text-[11px] font-black text-[#285b55] hover:underline"><ArrowLeft size={14} /> Back to sign in</Link></div> : null}
        </section>
      </div>
    </main>
  );
}
