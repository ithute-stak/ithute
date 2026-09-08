# BuildTrack monorepo migration

## Goal

Move BuildTrack from the initial hosted prototype to the standard Ithute Solutions deployment model without losing the product work already completed.

## Target shape

- \`apps/backend\`: FastAPI, SQLAlchemy, Alembic, API versions, background jobs and reporting services.
- \`apps/frontend\`: Next.js, TypeScript, role-specific portals and the BuildTrack interface.
- \`compose.yaml\`: PostgreSQL, Redis, migration, API and frontend services.
- \`.github/workflows\`: validation before merge and deployment.
- \`docs/\`: architecture, deployment, security and role documentation.

## Migration order

1. Establish the database schema and authenticated API contracts.
2. Move each existing BuildTrack module into the Next.js frontend:
   tenders, projects, people, fleet, subcontracts, documents and reports.
3. Add role-based permissions and audit history.
4. Add background notifications, exports and scheduled controls.
5. Enable release deployment only after all validation gates are green.

The legacy root application is retained temporarily so no existing work is discarded during the transition.
