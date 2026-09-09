"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Alert, Button } from "../components/ui";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

async function json<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { cache: "no-store", credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Request failed");
  return payload as T;
}

type ManualChallenge = {
  action: string;
  method: "post";
  fields: Record<string, string>;
};

function addFormField(form: HTMLFormElement, name: string, value: string) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = name;
  input.value = value;
  form.appendChild(input);
}

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
      const challenge = await json<ManualChallenge>(
        `/access/oidc/manual-challenge?returnTo=${encodeURIComponent(returnTo)}`,
      );
      if (challenge.method !== "post" || !challenge.action || !challenge.fields) {
        throw new Error("Could not prepare secure sign-in");
      }

      // Credentials are posted by the browser directly to central Ithute Auth.
      // They are never sent to or stored by the BuildTrack API.
      const centralForm = document.createElement("form");
      centralForm.method = "post";
      centralForm.action = challenge.action;
      centralForm.acceptCharset = "UTF-8";
      for (const [name, value] of Object.entries(challenge.fields)) addFormField(centralForm, name, value);
      addFormField(centralForm, "identifier", email.trim());
      addFormField(centralForm, "password", password);
      addFormField(centralForm, "mfa_code", mfaCode.trim());
      document.body.appendChild(centralForm);
      setPassword("");
      setMfaCode("");
      centralForm.submit();
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof Error ? err.message : "Could not start secure sign-in");
    }
  }

  return <main className={styles.screen}><PublicHeader showSignIn={false} /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Construction Management System · Lesotho</span></div></div>
    <p className={styles.eyebrow}>Ithute protected access</p><h1 className={styles.title}>Sign in to Nthane Brothers.</h1>
    <p className={styles.intro}>Use your email and password here, or continue through the full Ithute Auth sign-in page. Your password is still verified by central Ithute Auth and is not stored by Nthane Brothers BuildTrack.</p>
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
