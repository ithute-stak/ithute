import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function Home() {
  const store = await cookies();
  const signedIn = Boolean(store.get("nbros_access")?.value);

  if (signedIn) redirect("/fleet");

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
        <div className="foundation-card">
          <span className="eyebrow">NBros · Secure Operations Platform</span>
          <h1>Fleet Management starts here.</h1>
          <p>
            Manage branch-owned vehicles, compliance documents, services, mechanical
            condition, inspections, drivers, trips, reservations and operational readiness
            from one decision-driven system.
          </p>
          <div className="actions">
            <a className="primary" href="/api/auth/login">Sign in with !thute</a>
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
