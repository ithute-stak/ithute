"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="grid min-h-screen place-items-center bg-[#f4f6f4] p-5">
          <section className="w-full max-w-lg rounded-2xl border border-[#e1e7e3] bg-white p-8 text-center shadow-sm">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-red-50 text-red-700">
              <AlertTriangle size={24} />
            </div>
            <h1 className="mt-5 text-2xl font-black text-[#1f2f27]">Something went wrong</h1>
            <p className="mx-auto mt-2 max-w-md text-[12px] leading-5 text-[#718078]">
              The control plane could not render this view. Your data has not been changed by this error screen.
            </p>
            <button
              onClick={reset}
              className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl bg-[#123a38] px-4 text-xs font-black text-white"
            >
              <RefreshCw size={14} />
              Try again
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
