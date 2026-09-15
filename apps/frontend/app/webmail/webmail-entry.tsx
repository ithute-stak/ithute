"use client";

import Link from "next/link";
import {
  ArrowRight,
  Eye,
  EyeOff,
  Fingerprint,
  Loader2,
  LockKeyhole,
  Mail,
  MonitorSmartphone,
  ShieldCheck,
  UserRound,
  UsersRound,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { HostedMailWorkspace as MailClient } from "./hosted-workspace";
import { API, webmail } from "./mail-types";

type LoginMode = "mailbox" | "system";
type SessionState = "checking" | "guest" | "mailbox";

const features = [
  {
    title: "Professional email",
    detail: "Use your own domain with IMAP & SMTP",
    icon: Mail,
  },
  {
    title: "Secure & private",
    detail: "Protected sessions and verified connections",
    icon: ShieldCheck,
  },
  {
    title: "Work anywhere",
    detail: "Responsive on desktop, tablet and phone",
    icon: MonitorSmartphone,
  },
  {
    title: "Built for teams",
    detail: "A familiar inbox for everyday business",
    icon: UsersRound,
  },
];

function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <div className="imail-brand-row">
      <div className="imail-brand-mark">!T</div>
      <div>
        <p className="imail-brand-name" style={dark ? { color: "#ffffff" } : undefined}>Ithute Mail</p>
        <p className="imail-brand-kicker">Webmail</p>
      </div>
    </div>
  );
}

function InboxPreview() {
  return (
    <div className="imail-login-preview" aria-hidden="true">
      <div className="imail-login-preview-card">
        <div className="imail-login-preview-top">
          <span className="imail-login-preview-dot" />
          <span className="imail-login-preview-dot" />
          <span className="imail-login-preview-dot" />
        </div>
        <div className="imail-login-preview-body">
          <div className="imail-login-preview-side">
            {[1, 2, 3, 4, 5].map((item) => <div key={item} className="imail-login-preview-pill" />)}
          </div>
          <div className="imail-login-preview-list">
            {[78, 90, 70, 84, 65].map((width, index) => (
              <div key={`${width}-${index}`} className="imail-login-preview-row">
                <span className="imail-login-preview-avatar" />
                <div className="imail-login-preview-lines">
                  <span style={{ width: `${width}%` }} />
                  <span />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function WebmailEntry() {
  const [sessionState, setSessionState] = useState<SessionState>("checking");
  const [mode, setMode] = useState<LoginMode>("mailbox");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mailboxAddress, setMailboxAddress] = useState("");
  const [mailboxPassword, setMailboxPassword] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await webmail("/session");
        if (!active) return;
        setSessionState(response.ok ? "mailbox" : "guest");
      } catch {
        if (active) setSessionState("guest");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  function selectMode(nextMode: LoginMode) {
    setMode(nextMode);
    setError("");
    setShowPassword(false);
  }

  async function mailboxLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await webmail("/session", {
        method: "POST",
        body: JSON.stringify({ address: mailboxAddress.trim(), password: mailboxPassword }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(String(body.detail || "Mailbox login failed. Check the mailbox address and password."));
        return;
      }
      setSessionState("mailbox");
    } catch {
      setError("The mail service could not be reached. Please try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  if (sessionState === "checking") {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f6f9f8]">
        <div className="flex items-center gap-3 rounded-2xl border border-[#dce6e2] bg-white px-5 py-4 text-sm font-bold text-[#345047] shadow-sm">
          <Loader2 className="animate-spin text-[#087357]" size={18} />
          Opening Ithute Mail
        </div>
      </div>
    );
  }

  if (sessionState === "mailbox") return <MailClient />;

  return (
    <main className="imail-login-page">
      <div className="imail-login-shell">
        <section className="imail-login-hero">
          <Brand dark />

          <div className="imail-login-copy">
            <h1>Your business inbox,<br /><span>done right.</span></h1>
            <p>A modern, secure and reliable email workspace for business. Read and send mail from your Ithute-hosted mailbox with a familiar, focused experience.</p>
          </div>

          <div className="imail-login-features">
            {features.map(({ title, detail, icon: Icon }) => (
              <div key={title} className="imail-login-feature">
                <div className="imail-login-feature-icon"><Icon size={18} /></div>
                <div><strong>{title}</strong><span>{detail}</span></div>
              </div>
            ))}
          </div>

          <InboxPreview />
        </section>

        <section className="imail-login-panel">
          <div className="imail-login-form-wrap">
            <div className="imail-login-mobile-brand"><Brand /></div>

            <p className="imail-login-eyebrow">Ithute Mail • Webmail</p>
            <h2 className="imail-login-title">Sign in</h2>
            <p className="imail-login-subtitle">
              {mode === "mailbox"
                ? "Use your mailbox address and password to access your business inbox."
                : "Continue through centralized Ithute Auth for administration and system access."}
            </p>

            <div className="imail-login-mode" role="tablist" aria-label="Sign-in method">
              <button type="button" data-active={mode === "mailbox"} onClick={() => selectMode("mailbox")}>
                <Mail size={15} className="mr-1 inline" /> Mailbox
              </button>
              <button type="button" data-active={mode === "system"} onClick={() => selectMode("system")}>
                <UserRound size={15} className="mr-1 inline" /> System account
              </button>
            </div>

            {error ? <div role="alert" className="imail-login-error">{error}</div> : null}

            {mode === "mailbox" ? (
              <form onSubmit={mailboxLogin} className="imail-login-form">
                <div className="imail-field">
                  <label htmlFor="mailbox-address">Email address</label>
                  <div className="imail-input-wrap">
                    <Mail size={18} />
                    <input
                      id="mailbox-address"
                      type="email"
                      required
                      autoComplete="username"
                      value={mailboxAddress}
                      onChange={(event) => setMailboxAddress(event.target.value)}
                      placeholder="name@company.co.ls"
                    />
                  </div>
                </div>

                <div className="imail-field">
                  <label htmlFor="mailbox-password">Mailbox password</label>
                  <div className="imail-input-wrap">
                    <LockKeyhole size={18} />
                    <input
                      id="mailbox-password"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      value={mailboxPassword}
                      onChange={(event) => setMailboxPassword(event.target.value)}
                      placeholder="Your password"
                    />
                    <button type="button" className="imail-input-action" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>

                <div className="imail-login-meta">
                  <span>Protected mailbox session</span>
                  <span>Password managed by your mailbox administrator</span>
                </div>

                <button disabled={loading} className="imail-login-primary">
                  {loading ? <Loader2 size={18} className="animate-spin" /> : <Mail size={18} />}
                  {loading ? "Signing in…" : "Sign in"}
                  {!loading ? <ArrowRight size={17} /> : null}
                </button>
              </form>
            ) : (
              <div className="imail-login-form">
                <div className="imail-security-note">
                  <Fingerprint size={19} className="mt-0.5 shrink-0" />
                  <div>
                    <strong>Centralized Ithute Auth</strong>
                    <span>Your system password is handled only by Ithute Auth. Webmail no longer submits system credentials to the legacy Mailbox DNS login endpoint.</span>
                  </div>
                </div>

                <a href={`${API}/auth/ithute/login`} className="imail-login-primary">
                  <Fingerprint size={18} />
                  Continue with Ithute Auth
                  <ArrowRight size={17} />
                </a>

                <div className="imail-login-meta">
                  <span>Single sign-on for administration</span>
                  <span>MFA is handled by Ithute Auth when enabled</span>
                </div>
              </div>
            )}

            <div className="imail-login-divider">or</div>
            <Link href="/webmail/external" className="imail-login-secondary">
              <Mail size={18} /> Other email account <ArrowRight size={16} />
            </Link>

            <div className="imail-security-note">
              <ShieldCheck size={19} className="mt-0.5 shrink-0" />
              <div>
                <strong>Secure and private</strong>
                <span>Hosted mailbox credentials stay inside the encrypted server-side webmail session and connect to the verified production mail server.</span>
              </div>
            </div>

            <p className="imail-login-help">Need help? <Link href="/help">Open Ithute support</Link> or contact your administrator.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
