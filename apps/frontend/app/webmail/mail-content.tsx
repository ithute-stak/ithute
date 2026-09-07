"use client";

import { ExternalLink, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

const TOKEN_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\+?[0-9][0-9 ()-]{6,}[0-9])/gi;
const TRAILING_RE = /[),.;:!?]+$/;

function splitTrailing(value: string) {
  const match = value.match(TRAILING_RE);
  if (!match) return { token: value, trailing: "" };
  return { token: value.slice(0, -match[0].length), trailing: match[0] };
}

function hrefFor(token: string) {
  if (/^https?:\/\//i.test(token)) return token;
  if (/^www\./i.test(token)) return `https://${token}`;
  if (/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(token)) return `mailto:${token}`;
  const phone = token.replace(/[^+0-9]/g, "");
  if (/^\+?[0-9]{7,}$/.test(phone)) return `tel:${phone}`;
  return "";
}

export function linkifyText(value: string, openLinksNewTab = true): ReactNode[] {
  const output: ReactNode[] = [];
  let cursor = 0;
  let index = 0;
  for (const match of value.matchAll(TOKEN_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) output.push(value.slice(cursor, start));
    const raw = match[0];
    const { token, trailing } = splitTrailing(raw);
    const href = hrefFor(token);
    if (href) {
      const external = /^https?:/i.test(href);
      output.push(
        <a
          key={`mail-link-${index++}`}
          href={href}
          target={external && openLinksNewTab ? "_blank" : undefined}
          rel={external ? "noopener noreferrer nofollow" : undefined}
          className="break-words font-semibold text-[#0869d7] underline decoration-[#0869d7]/35 underline-offset-2 transition hover:text-[#064ca4] hover:decoration-current dark:text-[#68aaff] dark:hover:text-[#9ac7ff]"
        >
          {token}
        </a>,
      );
      if (trailing) output.push(trailing);
    } else {
      output.push(raw);
    }
    cursor = start + raw.length;
  }
  if (cursor < value.length) output.push(value.slice(cursor));
  return output;
}

type MailContentProps = {
  text: string;
  openLinksNewTab?: boolean;
  fontScale?: "small" | "normal" | "large";
  className?: string;
};

export function MailContent({ text, openLinksNewTab = true, fontScale = "normal", className = "" }: MailContentProps) {
  const scale = fontScale === "small" ? "text-[13px] leading-6" : fontScale === "large" ? "text-[16px] leading-8" : "text-[14px] leading-7";
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  return (
    <div className={`${scale} break-words text-slate-800 dark:text-slate-200 ${className}`}>
      {lines.map((line, index) => {
        const quoted = /^>/.test(line.trimStart());
        return (
          <div key={index} className={quoted ? "border-l-2 border-slate-200 pl-3 text-slate-500 dark:border-slate-700 dark:text-slate-400" : "min-h-[1.75em]"}>
            {line ? linkifyText(line, openLinksNewTab) : <br />}
          </div>
        );
      })}
    </div>
  );
}

export function MailPrivacyNote() {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-emerald-900/10 bg-emerald-50/70 px-3 py-2.5 text-[11px] leading-5 text-emerald-950 dark:border-emerald-400/10 dark:bg-emerald-400/[.06] dark:text-emerald-100">
      <ShieldCheck size={15} className="mt-0.5 shrink-0" />
      <span>iMail reads external messages as safe text. Links are detected and made clickable without executing remote email code or tracking images.</span>
      <ExternalLink size={13} className="mt-1 shrink-0 opacity-50" />
    </div>
  );
}
