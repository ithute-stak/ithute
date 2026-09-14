"use client";

import { Download, Printer } from "lucide-react";

export function CvPrintControls() {
  function printCv() {
    window.print();
  }

  return (
    <div className="mb-5 flex flex-wrap items-center justify-end gap-2 print:hidden">
      <button
        type="button"
        onClick={printCv}
        className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-[#d8e1dc] bg-white px-4 text-xs font-black text-[#285b55] shadow-sm transition hover:bg-[#f6f9f7]"
        title="Open the browser print dialog and choose Save as PDF"
      >
        <Download size={15} /> Save as PDF
      </button>
      <button
        type="button"
        onClick={printCv}
        className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-[#123a38] px-4 text-xs font-black text-white shadow-sm transition hover:bg-[#285b55]"
      >
        <Printer size={15} /> Print CV
      </button>
    </div>
  );
}
