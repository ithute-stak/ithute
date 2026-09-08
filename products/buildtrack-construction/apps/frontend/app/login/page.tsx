"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Alert, Button, FormField, Input } from "../components/ui";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Request failed");
  return payload as T;
}

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void json<{ company_bootstrapped: boolean; admin_bootstrapped: boolean }>("/access/setup-status")
      .then((status) => {
        if (!status.company_bootstrapped || !status.admin_bootstrapped) router.replace("/setup");
        else setReady(true);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load Nthane Brothers"));
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const result = await json<{ must_change_password: boolean }>("/access/login", { method: "POST", body: JSON.stringify({ username, password }) });
      const returnTo = params.get("returnTo");
      router.replace(result.must_change_password ? "/access?changePassword=1" : (returnTo?.startsWith("/") ? returnTo : "/"));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally { setBusy(false); }
  }

  return <main className={styles.screen}><PublicHeader showSignIn={false} /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Construction Management System · Lesotho</span></div></div>
    <p className={styles.eyebrow}>Secure role-based access</p><h1 className={styles.title}>Sign in to Nthane Brothers.</h1>
    <p className={styles.intro}>Your account determines which company, branch, site and operational modules you can access. Need help first? Use the Documentation &amp; User Manual button above.</p>
    {error && <Alert tone="danger" title="Sign-in unavailable">{error}</Alert>}
    {!ready ? <p className={styles.intro}>Checking system access…</p> : <form className={styles.form} onSubmit={submit}>
      <FormField label="Username or email" required><Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus /></FormField>
      <FormField label="Password" required><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></FormField>
      <Button type="submit" loading={busy}>{busy ? "Signing in…" : "Sign in securely"}</Button>
    </form>}
    <div className={styles.linkRow}><Link href="/reset-password">Use a reset token</Link><Link href="/index">Read the user manual</Link></div>
  </section></div></main>;
}
