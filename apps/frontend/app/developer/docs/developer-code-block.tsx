"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function DeveloperCodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="relative mt-5 overflow-hidden rounded-2xl border border-cyan-400/20 bg-[#0d1d30]">
      <div className="flex justify-end border-b border-white/10 px-3 py-2">
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? "Code copied" : "Copy code"}
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-cyan-400/50 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300"
        >
          {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-5 text-sm leading-7 text-cyan-100"><code>{code}</code></pre>
    </div>
  );
}
