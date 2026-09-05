"use client";

import { AlertTriangle, Home, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("!thute route error", error);
  }, [error]);

  return (
    <div className="grid min-h-[70vh] place-items-center p-4">
      <section className="surface-card w-full max-w-xl p-6 text-center sm:p-8">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-red-50 text-red-700">
          <AlertTriangle size={24} />
        </div>
        <p className="mt-5 text-[10px] font-black uppercase tracking-[.14em] text-[var(--admin-muted)]">!thute recovery</p>
        <h1 className="mt-1 text-2xl font-black tracking-tight text-[var(--admin-ink)]">This view could not load</h1>
        <p className="mx-auto mt-2 max-w-md text-[12px] leading-6 text-[var(--admin-muted)]">
          Your data has not been changed by this screen. You can retry the view or return to the command centre.
        </p>
        {error.digest ? <p className="mx-auto mt-3 w-fit rounded-lg bg-[var(--admin-soft)] px-2 py-1 font-mono text-[9px] text-[var(--admin-muted)]">Reference {error.digest}</p> : null}
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button onClick={reset} className="btn-primary"><RefreshCw size={14}/>Try again</button>
          <Link href="/dashboard" className="btn-secondary"><Home size={14}/>Command centre</Link>
        </div>
      </section>
    </div>
  );
}
