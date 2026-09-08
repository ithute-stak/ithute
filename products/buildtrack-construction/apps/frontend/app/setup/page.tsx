"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PublicHeader } from "../components/public-header";
import styles from "../security.module.css";

type Status = { company_bootstrapped: boolean; admin_bootstrapped: boolean; company_name?: string | null };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail ?? payload));
  return payload as T;
}

export default function SetupPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [company, setCompany] = useState({ name: "Nthane Brothers", legal_name: "Nthane Brothers", code: "NTHANE", head_office_name: "Head Office", head_office_code: "HO", head_office_district: "Maseru", phone: "", email: "", physical_address: "" });
  const [admin, setAdmin] = useState({ username: "admin", email: "", full_name: "", password: "", confirm: "", phone: "" });

  async function refresh() {
    try {
      const next = await api<Status>("/access/setup-status");
      if (next.company_bootstrapped && next.admin_bootstrapped) { router.replace("/login"); return; }
      setStatus(next);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not load setup"); }
  }
  useEffect(() => { void refresh(); }, []);

  async function createCompany(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api("/foundation/bootstrap", { method: "POST", body: JSON.stringify(company) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Company setup failed"); }
    finally { setBusy(false); }
  }

  async function createAdmin(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (admin.password !== admin.confirm) throw new Error("Passwords do not match");
      await api("/access/bootstrap-admin", { method: "POST", body: JSON.stringify({ username: admin.username, email: admin.email, full_name: admin.full_name, password: admin.password, phone: admin.phone || null }) });
      router.replace("/access"); router.refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Administrator setup failed"); }
    finally { setBusy(false); }
  }

  return <main className={styles.screen}><PublicHeader /><div className={styles.authWrap}><section className={styles.authCard}>
    <div className={styles.brand}><span className={styles.brandMark}>NB</span><div className={styles.brandText}><strong>Nthane Brothers</strong><span>Controlled first-time setup</span></div></div>
    <p className={styles.eyebrow}>Foundation + secure access bootstrap</p>
    {!status ? <><h1 className={styles.title}>Preparing Nthane Brothers.</h1><p className={styles.intro}>Checking the installation state…</p></> : !status.company_bootstrapped ? <>
      <h1 className={styles.title}>Establish the company.</h1><p className={styles.intro}>Create the single-company Nthane Brothers structure and Head Office before access accounts are enabled.</p>
      {error && <div className={`${styles.alert} ${styles.error}`}>{error}</div>}
      <form className={styles.form} onSubmit={createCompany}><div className={styles.grid2}>
        <label className={styles.field}><span>Company name</span><input value={company.name} onChange={(e)=>setCompany({...company,name:e.target.value})} required /></label>
        <label className={styles.field}><span>Legal name</span><input value={company.legal_name} onChange={(e)=>setCompany({...company,legal_name:e.target.value})} /></label>
        <label className={styles.field}><span>Company code</span><input value={company.code} onChange={(e)=>setCompany({...company,code:e.target.value.toUpperCase()})} required /></label>
        <label className={styles.field}><span>Head office</span><input value={company.head_office_name} onChange={(e)=>setCompany({...company,head_office_name:e.target.value})} required /></label>
        <label className={styles.field}><span>Head office code</span><input value={company.head_office_code} onChange={(e)=>setCompany({...company,head_office_code:e.target.value.toUpperCase()})} required /></label>
        <label className={styles.field}><span>District</span><input value={company.head_office_district} onChange={(e)=>setCompany({...company,head_office_district:e.target.value})} /></label>
        <label className={styles.field}><span>Phone</span><input value={company.phone} onChange={(e)=>setCompany({...company,phone:e.target.value})} /></label>
        <label className={styles.field}><span>Email</span><input type="email" value={company.email} onChange={(e)=>setCompany({...company,email:e.target.value})} /></label>
      </div><label className={styles.field}><span>Physical address</span><textarea value={company.physical_address} onChange={(e)=>setCompany({...company,physical_address:e.target.value})} /></label>
      <button className={`${styles.btn} ${styles.primary}`} disabled={busy}>{busy ? "Creating foundation…" : "Create company foundation"}</button></form>
    </> : <>
      <h1 className={styles.title}>Create the first administrator.</h1><p className={styles.intro}>{status.company_name} is ready. This account receives the System Administrator role and can create all other users.</p>
      {error && <div className={`${styles.alert} ${styles.error}`}>{error}</div>}
      <form className={styles.form} onSubmit={createAdmin}><div className={styles.grid2}>
        <label className={styles.field}><span>Full name</span><input value={admin.full_name} onChange={(e)=>setAdmin({...admin,full_name:e.target.value})} required /></label>
        <label className={styles.field}><span>Username</span><input autoComplete="username" value={admin.username} onChange={(e)=>setAdmin({...admin,username:e.target.value.toLowerCase()})} required /></label>
        <label className={styles.field}><span>Email</span><input type="email" value={admin.email} onChange={(e)=>setAdmin({...admin,email:e.target.value})} required /></label>
        <label className={styles.field}><span>Phone</span><input value={admin.phone} onChange={(e)=>setAdmin({...admin,phone:e.target.value})} /></label>
        <label className={styles.field}><span>Password</span><input type="password" autoComplete="new-password" value={admin.password} onChange={(e)=>setAdmin({...admin,password:e.target.value})} required /></label>
        <label className={styles.field}><span>Confirm password</span><input type="password" autoComplete="new-password" value={admin.confirm} onChange={(e)=>setAdmin({...admin,confirm:e.target.value})} required /></label>
      </div><div className={styles.asideNote}>Use at least 12 characters with uppercase, lowercase, a number and a special character. The security policy can be strengthened after setup.</div>
      <button className={`${styles.btn} ${styles.primary}`} disabled={busy}>{busy ? "Securing Nthane Brothers…" : "Create System Administrator"}</button></form>
    </>}
  </section></div></main>;
}
