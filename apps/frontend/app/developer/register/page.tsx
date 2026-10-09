"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import Script from "next/script";

export default function DeveloperRegister() {
  const [displayName,setDisplayName]=useState("");
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [confirm,setConfirm]=useState("");
  const [busy,setBusy]=useState(false);
  const [status,setStatus]=useState("");
  const [success,setSuccess]=useState(false);
  const [verificationToken,setVerificationToken]=useState("");
  const siteKey=process.env.NEXT_PUBLIC_ITHUTE_DEVELOPER_TURNSTILE_SITE_KEY;
  useEffect(()=>{const global=window as typeof window & {ithuteRegistrationVerified?:(token:string)=>void;ithuteRegistrationExpired?:()=>void};global.ithuteRegistrationVerified=(token:string)=>setVerificationToken(token);global.ithuteRegistrationExpired=()=>setVerificationToken("");return ()=>{delete global.ithuteRegistrationVerified;delete global.ithuteRegistrationExpired};},[]);
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if (!siteKey || !verificationToken){setStatus("Please complete the security verification.");return;}
    if (password!==confirm){setStatus("Passwords do not match.");return;}
    setBusy(true);setStatus("");
    try {
      const response=await fetch("/developer/api/register",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({display_name:displayName,email,password,verificationToken}),
      });
      const data=await response.json() as {message?:string};
      if(!response.ok){setStatus(data.message ?? "Registration could not be completed.");return;}
      setSuccess(true);setStatus("Your Ithute Auth account has been created. Sign in to continue; developer application access requires approval.");
      setPassword("");setConfirm("");
    }catch{setStatus("Registration service is unavailable. Please try again later.");}
    finally{setBusy(false);}
  }
  return <main className="flex min-h-screen items-center justify-center bg-[#07101e] px-5 py-16 text-slate-100"><div className="w-full max-w-lg rounded-3xl border border-white/10 bg-[#102034] p-8 shadow-2xl">
    <Link href="/developer" className="text-sm font-bold text-cyan-300">← Developer portal</Link>
    <h1 className="mt-6 text-3xl font-black">Create your developer account</h1>
    <p className="mt-3 text-sm leading-6 text-slate-300">Use your existing email address. Registering creates an Ithute identity, not an email mailbox or OAuth application.</p>
    {siteKey&&<Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive"/>}
    {!success&&<form onSubmit={submit} className="mt-7 grid gap-4">
      <label className="grid gap-2 text-sm font-semibold">Full name<input required maxLength={160} autoComplete="name" className="rounded-xl border border-white/15 bg-white/5 p-3 text-white" value={displayName} onChange={e=>setDisplayName(e.target.value)}/></label>
      <label className="grid gap-2 text-sm font-semibold">Email address<input required type="email" maxLength={320} autoComplete="email" className="rounded-xl border border-white/15 bg-white/5 p-3 text-white" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label className="grid gap-2 text-sm font-semibold">Password (at least 10 characters)<input required type="password" minLength={10} maxLength={128} autoComplete="new-password" className="rounded-xl border border-white/15 bg-white/5 p-3 text-white" value={password} onChange={e=>setPassword(e.target.value)}/></label>
      <label className="grid gap-2 text-sm font-semibold">Confirm password<input required type="password" minLength={10} maxLength={128} autoComplete="new-password" className="rounded-xl border border-white/15 bg-white/5 p-3 text-white" value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
      {siteKey?<div className="cf-turnstile" data-sitekey={siteKey} data-callback="ithuteRegistrationVerified" data-expired-callback="ithuteRegistrationExpired" />:<p className="text-sm text-amber-300">Public registration is not enabled yet.</p>}
      <button disabled={busy || !siteKey || !verificationToken} className="mt-2 rounded-xl bg-cyan-400 p-3 font-bold text-slate-950 disabled:opacity-60">{busy?"Creating account…":"Create account"}</button>
    </form>}
    {status&&<p role="status" className="mt-5 rounded-lg border border-white/15 bg-white/5 p-3 text-sm">{status}</p>}
    <div className="mt-7 border-t border-white/10 pt-5 text-sm text-slate-300"><Link href="/login" className="font-semibold text-cyan-300">Already registered? Sign in</Link><p className="mt-4">Want an @ithute.co.ls mailbox? <a className="text-cyan-300 underline" href="mailto:support@ithute.co.ls?subject=Ithute%20developer%20mailbox%20request">Request mailbox provisioning</a>.</p></div>
  </div></main>;
}
