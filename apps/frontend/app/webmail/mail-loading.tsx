"use client";

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
      <div className="imail-mail-loader-card">
        <div className="imail-mail-loader-logo" aria-hidden="true" />
        <div className="imail-mail-loader-ring" aria-hidden="true" />
        <div className="imail-mail-loader-copy">
          <p className="imail-mail-loader-title">{label}</p>
          <p className="imail-mail-loader-detail">{detail}</p>
        </div>
      </div>
    </div>
  );
}
