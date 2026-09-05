import Link from "next/link";
import { WebmailEntry } from "./webmail-entry";

export default function WebmailPage() {
  return (
    <div className="relative">
      <WebmailEntry />
      <Link
        href="/webmail/external"
        className="fixed bottom-4 left-4 z-[75] inline-flex min-h-10 items-center rounded-full border border-[#cddbd5] bg-white/95 px-4 text-xs font-extrabold text-[#245c4d] shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:bg-[#f2f8f5]"
      >
        Other email account
      </Link>
    </div>
  );
}
