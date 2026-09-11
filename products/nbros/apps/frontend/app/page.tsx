import { cookies } from "next/headers";
import { redirect } from "next/navigation";

type HomeProps = {
  searchParams: Promise<{ auth_error?: string | string[] }>;
};

function authErrorMessage(value: string | string[] | undefined): string | null {
  const code = Array.isArray(value) ? value[0] : value;
  switch (code) {
    case "missing_credentials":
      return "Enter your email and password to continue.";
    case "invalid_credentials":
      return "The email or password is incorrect.";
    case "mfa_required":
      return "Enter your authenticator or recovery code and try again.";
    case "too_many_attempts":
      return "Too many sign-in attempts. Please wait a few minutes and try again.";
    case "auth_unavailable":
      return "Ithute Auth is temporarily unavailable. Please try again.";
    case "auth_response_invalid":
      return "Ithute Auth returned an invalid session. Please try again.";
    case "invalid_callback":
    case "token_exchange_failed":
    case "id_token_missing":
    case "id_token_invalid":
      return "Ithute single sign-on could not complete. Please try again.";
    default:
      return null;
  }
}

export default async function Home({ searchParams }: HomeProps) {
  const store = await cookies();
  const signedIn = Boolean(store.get("nbros_access")?.value);

  if (signedIn) redirect("/fleet");

  const params = await searchParams;
  const authError = authErrorMessage(params.auth_error);

  return (
    <main className="foundation-page">
      <header className="brand-header">
        <div className="brand-lockup">
          <div className="brand-mark">NB</div>
          <div>
            <strong>Nthane Brothers</strong>
            <span>NBros Management Platform</span>
          </div>
        </div>
        <span className="ithute-credit">Powered by !thute</span>
      </header>
      <div className="slate-band" />
      <section className="foundation-stage">
        <div className="foundation-card login-card">
          <div className="login-layout">
            <div className="login-intro">
              <span className="eyebrow">NBros · Secure Operations Platform</span>
              <h1>Fleet Management starts here.</h1>
              <p>
                Manage branch-owned vehicles, compliance documents, services, mechanical
                condition, inspections, drivers, trips, reservations and operational readiness
                from one decision-driven system.
              </p>
              <div className="login-security-note">
                <strong>Central identity</strong>
                <span>Your password is verified by Ithute Auth and is never stored by NBros.</span>
              </div>
            </div>

            <div className="login-panel">
              <div>
                <span className="eyebrow">Sign in</span>
                <h2>Welcome back</h2>
                <p>Use your NBros email and password.</p>
              </div>

              {authError ? <div className="login-error" role="alert">{authError}</div> : null}

              <form className="login-form" method="post" action="/api/auth/password">
                <label>
                  Email
                  <input
                    type="email"
                    name="identifier"
                    defaultValue="justy@ithute.co.ls"
                    autoComplete="username"
                    required
                  />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    name="password"
                    autoComplete="current-password"
                    required
                  />
                </label>
                <details className="login-mfa">
                  <summary>Authenticator or recovery code</summary>
                  <label>
                    Code
                    <input
                      name="mfa_code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="Only if MFA is enabled"
                    />
                  </label>
                </details>
                <button className="primary-button login-submit" type="submit">Sign in</button>
              </form>

              <div className="login-divider"><span>or</span></div>
              <a className="ghost-button login-sso" href="/api/auth/login">Sign in with Ithute SSO</a>
            </div>
          </div>
        </div>
      </section>
      <footer className="brand-footer">
        <strong>NTHANE BROTHERS</strong>
        <span>NBros · Fleet Management System</span>
      </footer>
    </main>
  );
}
