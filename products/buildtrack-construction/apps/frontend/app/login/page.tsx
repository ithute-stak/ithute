"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Alert, Button } from "../components/ui";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

const CENTRAL_AUTH_LOGIN = "https://auth.ithute.co.ls/v1/auth/login";
const BUILDTRACK_CLIENT_ID = "buildtrack-construction";

async function json<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { cache: "no-store", credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Request failed");
  return payload as T;
}

type CentralTokens = {
  access_token: string;
  refresh_token: string;
};

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const returnTo = useMemo(() => {
    const value = params.get("returnTo");
    return value?.startsWith("/") && !value.startsWith("//") ? value : "/";
  }, [params]);
  const centralLogin = `/api/v1/access/oidc/login?returnTo=${encodeURIComponent(returnTo)}`;

  useEffect(() => {
    void json<{ company_bootstrapped: boolean; admin_bootstrapped: boolean }>("/access/setup-status")
      .then((status) => {
        if (!status.company_bootstrapped || !status.admin_bootstrapped) router.replace("/setup");
        else setReady(true);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load Nthane Brothers"));
  }, [router]);

  async function submitEmailPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || submitting) return;
    setError("");
    setSubmitting(true);

    try {
      // The browser sends the credential directly to central Ithute Auth. BuildTrack
      // receives only the resulting audience-bound tokens and never receives the password.
      const centralResponse = await fetch(CENTRAL_AUTH_LOGIN, {
        method: "POST",
        mode: "cors",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: BUILDTRACK_CLIENT_ID,
          identifier: email.trim(),
          password,
          mfa_code: mfaCode.trim() || null,
        }),
      });
      const centralPayload = await centralResponse.json().catch(() => ({}));
      if (!centralResponse.ok) {
        const detail = typeof centralPayload?.detail === "string" ? centralPayload.detail : "Central Ithute Auth rejected the sign-in";
        throw new Error(detail);
      }

      const tokens = centralPayload as Partial<CentralTokens>;
      if (!tokens.access_token || !tokens.refresh_token) {
        throw new Error("Central Ithute Auth returned an incomplete sign-in response");
      }

      const sessionResponse = await fetch("/api/v1/access/central-session", {
        method: "POST",
        cache: "no-store",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: tokens.access_token, refresh_token: tokens.refresh_token }),
      });
      const sessionPayload = await sessionResponse.json().catch(() => ({}));
      if (!sessionResponse.ok) {
        const detail = typeof sessionPayload?.detail === "string" ? sessionPayload.detail : "Nthane Brothers could not create your session";
        throw new Error(detail);
      }

      setPassword("");
      setMfaCode("");
      router.replace(returnTo);
      router.refresh();
    } catch (err) {
      setPassword("");
      setMfaCode("");
      setSubmitting(false);
      setError(err instanceof Error ? err.message : "Could not complete secure sign-in");
    }
  }

  return <main className={styles.screen}><PublicHeader showSignIn={false} /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Construction Management System · Lesotho</span></div></div>
    <p className={styles.eyebrow}>Ithute protected access</p><h1 className={styles.title}>Sign in to Nthane Brothers.</h1>
    <p className={styles.intro}>Use your email and password here. Your browser sends the credential directly to central Ithute Auth; Nthane Brothers receives only the resulting secure tokens and creates your BuildTrack session.</p>
    {error && <Alert tone="danger" title="Sign-in unavailable">{error}</Alert>}
    {!ready ? <p className={styles.intro}>Checking product readiness…</p> : <>
      <form className={styles.form} onSubmit={submitEmailPassword}>
        <label className={styles.field}>Email
          <input type="email" name="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@ithute.co.ls" required disabled={submitting} />
        </label>
        <label className={styles.field}>Password
          <input type="password" name="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={submitting} />
        </label>
        <label className={styles.field}>Authenticator or recovery code <span className={styles.muted}>(only if MFA is enabled)</span>
          <input name="mfa_code" autoComplete="one-time-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} disabled={submitting} />
        </label>
        <Button type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in with email & password"}</Button>
      </form>
      <p className={styles.intro} style={{ marginBottom: 12, textAlign: "center" }}>or</p>
      <a href={centralLogin} style={{ textDecoration: "none" }}><Button type="button">Continue with Ithute Auth</Button></a>
      <div className={styles.linkRow}><a href="https://auth.ithute.co.ls/forgot-password" rel="noreferrer">Set or reset password</a><a href="https://auth.ithute.co.ls/" rel="noreferrer">Ithute account</a></div>
    </>}
    <p className={styles.intro}>External vendors using a secure evidence link do not need an internal account. Product access remains role- and site-scoped after authentication.</p>
    <div className={styles.linkRow}><Link href="/index">Read the user manual</Link></div>
  </section></div></main>;
}
