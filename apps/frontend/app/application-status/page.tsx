"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, BadgeCheck, Building2, Clock3, Mail, ShieldCheck, XCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Application = {
  company_name: string;
  status: "pending" | "approved" | "rejected";
  requested_plan_code?: string | null;
  created_at?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string | null;
  applicant?: { email?: string | null; email_verified?: boolean };
};

export default function ApplicationStatusPage() {
  const [application, setApplication] = useState<Application | null | undefined>(undefined);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch(`${API}/me/customer-application`, { credentials: "include", cache: "no-store" })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(String(body.detail || "Unable to load your application"));
        setApplication(body.application ?? null);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Unable to load your application");
        setApplication(null);
      });
  }, []);

  if (application === undefined) {
    return <main className="grid min-h-screen place-items-center bg-[#eef3f0] text-sm font-semibold text-[#718078]">Checking your Ithute application…</main>;
  }

  const pending = application?.status === "pending";
  const approved = application?.status === "approved";
  const rejected = application?.status === "rejected";

  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#eef3f0] px-5 py-10 text-[#20342a]">
      <div className="absolute -left-32 top-0 h-96 w-96 rounded-full bg-[#d8c56a]/12 blur-3xl" />
      <div className="absolute -right-32 bottom-0 h-96 w-96 rounded-full bg-[#285b55]/10 blur-3xl" />
      <section className="relative w-full max-w-3xl overflow-hidden rounded-[30px] border border-[#d9e3dd] bg-white shadow-[0_30px_90px_rgba(18,58,56,.13)]">
        <div className="bg-[#123a38] px-7 py-6 text-white sm:px-9">
          <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#d8c56a] text-xl font-black text-[#123a38]">!</span><div><p className="font-black tracking-[-.03em]">thute</p><p className="text-[8px] font-black uppercase tracking-[.17em] text-white/45">Customer onboarding</p></div></div>
        </div>
        <div className="p-7 sm:p-9">
          {error ? <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}
          {!application ? (
            <div className="text-center"><Building2 className="mx-auto text-[#56746b]" size={30} /><h1 className="mt-4 text-2xl font-black">No customer application is attached to this account.</h1><p className="mt-3 text-sm leading-6 text-[#718078]">If you already have an active organization, continue to the Control Centre.</p><Link href="/dashboard" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#123a38] px-5 py-3 text-sm font-black text-white">Go to dashboard <ArrowRight size={15} /></Link></div>
          ) : (
            <>
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#718078]">{application.requested_plan_code || "Ithute"} application</p><h1 className="mt-2 text-3xl font-black tracking-[-.045em]">{application.company_name}</h1><p className="mt-2 flex items-center gap-2 text-xs font-semibold text-[#718078]"><Mail size={14} /> {application.applicant?.email || "Your verified account"}</p></div>
                <div className={`inline-flex items-center gap-2 self-start rounded-full px-3 py-2 text-[10px] font-black uppercase tracking-[.1em] ${pending ? "bg-amber-50 text-amber-700" : approved ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{pending ? <Clock3 size={14} /> : approved ? <BadgeCheck size={14} /> : <XCircle size={14} />}{application.status}</div>
              </div>

              {pending ? <div className="mt-7 rounded-2xl border border-amber-100 bg-[#fffaf0] p-5"><div className="flex gap-3"><Clock3 className="mt-0.5 shrink-0 text-amber-700" size={20} /><div><h2 className="font-black text-amber-900">Awaiting Ithute administrator approval</h2><p className="mt-2 text-xs leading-6 text-amber-800/80">Your company has been registered, but hosting, DNS, mailboxes, databases and other tenant services remain locked until an Ithute administrator reviews and approves the application. Your 14-day trial has not started yet.</p></div></div></div> : null}
              {approved ? <div className="mt-7 rounded-2xl border border-emerald-100 bg-emerald-50 p-5"><div className="flex gap-3"><BadgeCheck className="mt-0.5 shrink-0 text-emerald-700" size={20} /><div><h2 className="font-black text-emerald-900">Your company is approved</h2><p className="mt-2 text-xs leading-6 text-emerald-800/80">Your Ithute services are active and the selected trial/subscription entitlement is available. Continue to the Control Centre to configure your organization.</p></div></div></div> : null}
              {rejected ? <div className="mt-7 rounded-2xl border border-red-100 bg-red-50 p-5"><div className="flex gap-3"><XCircle className="mt-0.5 shrink-0 text-red-700" size={20} /><div><h2 className="font-black text-red-900">This application was not approved</h2><p className="mt-2 text-xs leading-6 text-red-800/80">{application.rejection_reason || "Please contact Ithute if you need more information about this decision."}</p></div></div></div> : null}

              <div className="mt-7 flex flex-wrap gap-3 border-t border-[#e8eeea] pt-6">
                {approved ? <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-xl bg-[#123a38] px-5 py-3 text-sm font-black text-white">Open Control Centre <ArrowRight size={15} /></Link> : null}
                <Link href="/" className="inline-flex items-center gap-2 rounded-xl border border-[#d8e2dd] px-5 py-3 text-sm font-black text-[#456057]">Ithute home</Link>
              </div>
            </>
          )}
          <div className="mt-7 flex items-center gap-2 rounded-xl bg-[#f8faf9] p-3 text-[10px] leading-5 text-[#718078]"><ShieldCheck size={15} className="shrink-0 text-[#56746b]" /> Approval state is enforced by the Ithute control plane, not only by this screen.</div>
        </div>
      </section>
    </main>
  );
}
