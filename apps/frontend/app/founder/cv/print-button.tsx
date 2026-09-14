"use client";

import { Download, Printer } from "lucide-react";

export function CvPrintControls() {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-end gap-2 print:hidden">
      <a
        href="/documents/Koetlisi-Theko-CV"
        download
        className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-[#d8e1dc] bg-white px-4 text-xs font-black text-[#285b55] shadow-sm transition hover:bg-[#f6f9f7]"
      >
        <Download size={15} /> Download PDF
      </a>
      <button
        type="button"
        onClick={() => window.print()}
        className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-[#123a38] px-4 text-xs font-black text-white shadow-sm transition hover:bg-[#285b55]"
      >
        <Printer size={15} /> Print CV
      </button>
    </div>
  );
}
