import type { ReactNode } from "react";
import { MailRealtime } from "./mail-realtime";
import styles from "./webmail.module.css";
import "./source-skin.css";

export default function WebmailLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`${styles.surface} sourceGmailSkin`}>
      <MailRealtime />
      {children}
    </div>
  );
}
