import Link from "next/link";
import styles from "./public-header.module.css";

export function PublicHeader({ showSignIn = true }: { showSignIn?: boolean }) {
  return <header className={styles.header}>
    <Link href="/index" className={styles.brand} aria-label="Nthane Brothers system manual and about">
      <span className={styles.mark}>NB</span>
      <span className={styles.copy}><strong>Nthane Brothers</strong><span>Construction Management System · Ithute Solution</span></span>
    </Link>
    <nav className={styles.actions} aria-label="Public navigation">
      <Link className={styles.link} href="/index"><span className={styles.dot} /> <span className={styles.desktop}>Documentation &amp; </span>User Manual</Link>
      {showSignIn ? <Link className={`${styles.link} ${styles.primary}`} href="/login">Sign in</Link> : null}
    </nav>
  </header>;
}
