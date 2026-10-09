# Developer Portal deployment verification

The developer portal and authenticated dashboard are merged into `main`, but a GitHub merge does **not** prove the running production image includes them.

## Before rollout

1. Confirm all release CI checks are green, including security and auth browser tests.
2. Ensure the central Auth service is enabled and reachable from the backend, with the existing OAuth application and exact approved callback `https://ithute.co.ls/api/v1/auth/ithute/callback`.
3. Apply the central Auth migrations, including developer access request storage, and confirm the database contains the expected schema.
4. Configure the developer signup's internal Auth URL and Turnstile site/secret keys; apply distributed rate limits and verify email ownership before activating services.
5. Check the deployed image SHA matches the intended `main` release, using your existing verified `pull ithute latest` process only after approving deployment.
6. Never print, copy or store credentials in terminal logs or smoke-test artifacts.

## Public read-only smoke test

```bash
python3 scripts/check-developer-portal.py https://ithute.co.ls
```

This tests five public HTML routes, anonymous registration rejection, and anonymous developer request protection. It does **not** sign in or mutate accounts. A failure means investigation is required, not that credentials should be bypassed.

## Authenticated acceptance checks

Use a dedicated test identity with verified email and a real approved central Auth application.

1. Open `/developer/dashboard` in a private browser. It must show a central sign-in prompt instead of a token input.
2. Complete OAuth sign-in and confirm the dashboard loads request history.
3. Submit an access request. Confirm it is visible only to the same identity and marked pending.
4. Log in as a properly elevated platform owner and review the request in `/ithute-platform`.
5. Record an approval or rejection. Confirm an audit entry and updated developer request status.
6. Verify that approval **does not** provision API keys, mailboxes or privileges automatically.
7. Revoke the central Auth session and confirm the dashboard account API refuses subsequent requests.
8. Confirm cross-origin request submissions are rejected; repeat with an unverified email identity and confirm rejection.
9. Confirm full logout, repeated logins, and expected behavior during central Auth outages.

## Rollback

If the rollout fails, stop new registrations and roll back using the last known-good approved production image, preserving migrated data. Check schema compatibility before rollback; do not automatically downgrade a live database. Record release SHA, deployment timestamp and smoke results.

**Important:** These tests cannot be represented as completed until executed against the actual deployed production image.
