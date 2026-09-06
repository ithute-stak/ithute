"use client";

import { Mail, Sparkles } from "lucide-react";

type MailLoadingProps = {
  label?: string;
  detail?: string;
  compact?: boolean;
};

export function MailLoading({
  label = "Opening iMail",
  detail = "Preparing your secure mailbox",
  compact = false,
}: MailLoadingProps) {
  if (compact) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-emerald-950/10 bg-white/95 px-4 py-3 shadow-lg shadow-emerald-950/5 backdrop-blur dark:border-white/10 dark:bg-slate-900/95">
        <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-emerald-950 to-emerald-700 text-amber-300">
          <Mail size={17} />
          <span className="absolute -right-1 -top-1 h-3 w-3 animate-pulse rounded-full border-2 border-white bg-amber-400 dark:border-slate-900" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-extrabold text-slate-800 dark:text-slate-100">{label}</span>
          <span className="block truncate text-[11px] font-medium text-slate-500 dark:text-slate-400">{detail}</span>
        </span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,.09),transparent_32%),linear-gradient(180deg,#f8fbfa,#eef4f1)] p-3 text-slate-800 dark:bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,.13),transparent_30%),linear-gradient(180deg,#0b1412,#101817)] dark:text-slate-100 sm:p-5">
      <div className="mx-auto grid min-h-[calc(100vh-40px)] max-w-[1500px] grid-cols-1 overflow-hidden rounded-[28px] border border-emerald-950/10 bg-white/85 shadow-[0_30px_90px_rgba(20,55,45,.10)] backdrop-blur md:grid-cols-[250px_1fr] dark:border-white/10 dark:bg-slate-950/65">
        <aside className="hidden border-r border-slate-200/70 bg-emerald-950/[.025] p-5 md:block dark:border-white/10 dark:bg-white/[.025]">
          <div className="flex items-center gap-3">
            <div className="relative grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-emerald-950 via-emerald-800 to-emerald-600 text-amber-300 shadow-lg shadow-emerald-950/15">
              <Mail size={21} />
              <Sparkles size={10} className="absolute -right-1 -top-1 text-amber-400" />
            </div>
            <div>
              <div className="text-xl font-black tracking-tight text-emerald-950 dark:text-emerald-100">iMail</div>
              <div className="text-[10px] font-bold uppercase tracking-[.18em] text-amber-600 dark:text-amber-300">ithute mail</div>
            </div>
          </div>
          <div className="mt-8 h-12 animate-pulse rounded-2xl bg-emerald-900/10 dark:bg-white/10" />
          <div className="mt-5 space-y-2.5">
            {[82, 68, 76, 64, 72, 58].map((width, index) => (
              <div key={index} className="flex h-9 items-center gap-3 rounded-xl px-2">
                <span className="h-5 w-5 animate-pulse rounded-md bg-slate-200 dark:bg-slate-700" />
                <span className="h-3 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" style={{ width: `${width}%` }} />
              </div>
            ))}
          </div>
        </aside>

        <section className="min-w-0 p-4 sm:p-6">
          <div className="mx-auto flex max-w-5xl flex-col gap-4">
            <div className="flex items-center justify-center py-8 sm:py-11">
              <div className="text-center">
                <div className="relative mx-auto grid h-20 w-20 place-items-center rounded-[24px] bg-gradient-to-br from-emerald-950 via-emerald-800 to-emerald-600 text-amber-300 shadow-[0_18px_40px_rgba(6,78,59,.25)]">
                  <Mail size={34} />
                  <span className="absolute inset-[-7px] animate-[spin_2.4s_linear_infinite] rounded-[30px] border border-transparent border-t-amber-400/90 border-r-emerald-500/40" />
                </div>
                <h1 className="mt-5 text-xl font-black tracking-tight text-emerald-950 dark:text-white">{label}</h1>
                <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">{detail}</p>
              </div>
            </div>

            <div className="h-14 animate-pulse rounded-2xl bg-slate-100 dark:bg-white/5" />
            <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 dark:border-white/10 dark:bg-white/[.035]">
              {[88, 73, 81, 66, 79, 69].map((width, index) => (
                <div key={index} className="flex items-center gap-3 border-b border-slate-100 px-4 py-3.5 last:border-0 dark:border-white/5">
                  <span className="h-9 w-9 shrink-0 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
                  <span className="w-28 shrink-0 space-y-2">
                    <span className="block h-3 w-20 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
                    <span className="block h-2.5 w-12 animate-pulse rounded-full bg-slate-100 dark:bg-slate-800" />
                  </span>
                  <span className="min-w-0 flex-1 space-y-2">
                    <span className="block h-3 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" style={{ width: `${width}%` }} />
                    <span className="block h-2.5 w-3/5 animate-pulse rounded-full bg-slate-100 dark:bg-slate-800" />
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
