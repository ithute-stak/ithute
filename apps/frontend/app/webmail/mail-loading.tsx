"use client";

import { Mail } from "lucide-react";

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
  return (
    <div
      className="imail-mail-loader"
      data-compact={compact ? "true" : "false"}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="imail-mail-loader-orb imail-mail-loader-orb-one" aria-hidden="true" />
      <div className="imail-mail-loader-orb imail-mail-loader-orb-two" aria-hidden="true" />
      <div className="imail-mail-loader-card">
        <div className="imail-mail-loader-brand" aria-hidden="true">
          <div className="imail-mail-loader-mark">
            <Mail size={27} strokeWidth={2.2} />
            <span className="imail-mail-loader-mark-dot" />
          </div>
          <div className="imail-mail-loader-wordmark">
            <strong>iMail</strong>
            <span>by Ithute</span>
          </div>
        </div>
        <div className="imail-mail-loader-ring" aria-hidden="true" />
        <div className="imail-mail-loader-copy">
          <p className="imail-mail-loader-title">{label}</p>
          <p className="imail-mail-loader-detail">{detail}</p>
        </div>
      </div>
    </div>
  );
}
