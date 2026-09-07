import type { ReactNode } from "react";
import { MailLinkEnhancer } from "./mail-link-enhancer";
import { MailRealtime } from "./mail-realtime";
import { WebmailMobileActions } from "./webmail-mobile-actions";
import { WebmailRouteFrame } from "./webmail-route-frame";
import styles from "./webmail.module.css";
import "./source-skin.css";
import "./mobile-responsive.css";
import "./mobile-responsive-polish.css";
import "./approved-webmail.css";
import "./approved-settings.css";

export default function WebmailLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`${styles.surface} sourceGmailSkin`}>
      <MailRealtime />
      <MailLinkEnhancer />
      <WebmailRouteFrame>{children}</WebmailRouteFrame>
      <WebmailMobileActions />
    </div>
  );
}
