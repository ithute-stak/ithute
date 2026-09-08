"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Alert, Button, FormField, Input, Textarea } from "../components/ui";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      if (password !== confirm) throw new Error("Passwords do not match");
      const response = await fetch("/api/v1/access/reset-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: token.trim(), new_password: password }) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not reset password");
      setMessage(payload.message ?? "Password reset. You can sign in now."); setPassword(""); setConfirm("");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not reset password"); }
    finally { setBusy(false); }
  }

  return <main className={styles.screen}><PublicHeader /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Secure password recovery</span></div></div>
    <p className={styles.eyebrow}>One-time reset</p><h1 className={styles.title}>Set a new password.</h1>
    <p className={styles.intro}>Enter the reset token issued by an authorised Nthane Brothers access administrator. Tokens expire automatically and can only be used once.</p>
    {error && <Alert tone="danger" title="Password not reset">{error}</Alert>}{message && <Alert tone="success" title="Password reset">{message}</Alert>}
    <form className={styles.form} onSubmit={submit}>
      <FormField label="Reset token" required description="Use the one-time token supplied by an authorised access administrator."><Textarea value={token} onChange={(e)=>setToken(e.target.value)} required rows={3} /></FormField>
      <FormField label="New password" required><Input type="password" autoComplete="new-password" value={password} onChange={(e)=>setPassword(e.target.value)} required /></FormField>
      <FormField label="Confirm new password" required><Input type="password" autoComplete="new-password" value={confirm} onChange={(e)=>setConfirm(e.target.value)} required /></FormField>
      <Button type="submit" loading={busy}>{busy ? "Resetting…" : "Reset password"}</Button>
    </form><div className={styles.linkRow}><Link href="/login">Back to sign in</Link><Link href="/index">User manual</Link></div>
  </section></div></main>;
}
