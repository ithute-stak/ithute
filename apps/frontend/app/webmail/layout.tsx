import type { ReactNode } from "react";
import { MailLinkEnhancer } from "./mail-link-enhancer";
import { MailMigrationShortcut } from "./mail-migration-shortcut";
import { MailRealtime } from "./mail-realtime";
import { MailSettingsThemeEnhancer } from "./mail-settings-theme-enhancer";
import { MailThemeBridge } from "./mail-theme-bridge";
import { WebmailMobileActions } from "./webmail-mobile-actions";
import { WebmailRouteFrame } from "./webmail-route-frame";
import styles from "./webmail.module.css";
import "./source-skin.css";
import "./mobile-responsive.css";
import "./mobile-responsive-polish.css";
import "./approved-webmail.css";
import "./approved-settings.css";
import "./external-workspace-fix.css";
import "./external-connect-premium.css";
import "./internal-webmail-premium.css";
import "./internal-message-content.css";
import "./mailbox-brand-unified.css";
import "./internal-webmail-live-scope.css";
import "./mail-settings-responsive.css";
import "./mail-theme-unified.css";
import "./mail-white600.css";
import "./mail-workspace-unified.css";
import "./hosted-workspace-polish.css";
import "./hosted-message-stability.css";

export default function WebmailLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`${styles.surface} sourceGmailSkin`}>
      <MailThemeBridge />
      <MailSettingsThemeEnhancer />
      <MailRealtime />
      <MailLinkEnhancer />
      <WebmailRouteFrame>{children}</WebmailRouteFrame>
      <MailMigrationShortcut />
      <WebmailMobileActions />
    </div>
  );
}
