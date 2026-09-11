import { cookies } from "next/headers";

export default async function Home() {
  const store = await cookies();
  const signedIn = Boolean(store.get("nbros_access")?.value);

  return (
    <main>
      <section className="card">
        <div className="badge">Ithute Solutions · NBros</div>
        <h1>NBros foundation is ready.</h1>
        <p>
          Central authentication, product-owned PostgreSQL and Redis, Alembic migrations,
          FastAPI, Next.js, and the central Ithute realtime contract are prepared. Business
          functionality will begin only after the project description is supplied.
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
      </section>
    </main>
  );
}
