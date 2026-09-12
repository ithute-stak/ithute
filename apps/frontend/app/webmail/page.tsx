import { WebmailExternalShortcut } from "./webmail-external-shortcut";
import { WebmailShell } from "./webmail-shell";

export default function WebmailPage() {
  return (
    <div className="relative">
      <WebmailShell />
      <WebmailExternalShortcut />
    </div>
  );
}
