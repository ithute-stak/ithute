"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Alert, Button } from "../components/ui";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

async function json<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { cache: "no-store", credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Request failed");
  return payload as T;
}

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

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

  return <main className={styles.screen}><PublicHeader showSignIn={false} /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Construction Management System · Lesotho</span></div></div>
    <p className={styles.eyebrow}>Ithute protected access</p><h1 className={styles.title}>Sign in to Nthane Brothers.</h1>
    <p className={styles.intro}>Identity and passwords are managed by central Ithute Auth. Your Nthane Brothers profile then determines your company, branch, site and operational permissions.</p>
    {error && <Alert tone="danger" title="Sign-in unavailable">{error}</Alert>}
    {!ready ? <p className={styles.intro}>Checking product readiness…</p> : <a href={centralLogin} style={{ textDecoration: "none" }}><Button type="button">Continue with Ithute Auth</Button></a>}
    <p className={styles.intro}>External vendors using a secure evidence link do not need an internal account. Product access remains role- and site-scoped after authentication.</p>
    <div className={styles.linkRow}><Link href="/index">Read the user manual</Link><a href="https://auth.ithute.co.ls/" rel="noreferrer">Ithute account</a></div>
  </section></div></main>;
}
