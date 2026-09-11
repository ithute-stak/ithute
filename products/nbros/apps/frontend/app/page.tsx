import { cookies } from "next/headers";

export default async function Home() {
  const store = await cookies();
  const signedIn = Boolean(store.get("nbros_access")?.value);

  return (
    <main className="foundation-page">
      <header className="brand-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">NB</div>
          <div className="brand-name">
            <strong>Nthane Brothers</strong>
            <span>NBros management platform</span>
          </div>
        </div>
        <div className="status-pill">Powered by Ithute Solutions</div>
      </header>
      <div className="brand-subbar" aria-hidden="true" />

      <section className="hero-stage">
        <div className="card">
          <div className="badge">Nthane Brothers · NBros</div>
          <h1>NBros</h1>
          <p>
            The new Nthane Brothers product foundation is ready. Central authentication,
            product-owned PostgreSQL and Redis, Alembic migrations, FastAPI, Next.js,
            and Ithute central realtime are prepared. Business functionality will begin
            from the project description you provide next.
          </p>
          <div className="actions">
            {!signedIn ? (
              <a className="primary" href="/api/auth/login">Sign in with !thute</a>
            ) : (
              <form action="/api/auth/logout" method="post">
                <button className="secondary" type="submit">Sign out</button>
              </form>
            )}
          </div>
        </div>
      </section>

      <footer className="brand-footer">Nthane Brothers · NBros</footer>
    </main>
  );
}
