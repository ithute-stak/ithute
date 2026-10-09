# Developer registration and email

## Register with your existing address

Use `/developer/register`. The browser form submits name, email and password to the same-origin `/developer/api/register` route. The Next.js server validates an anti-bot challenge and proxies registration to the central Auth `POST /v1/users/register` endpoint.

Production configuration requires `ITHUTE_AUTH_INTERNAL_URL`, `ITHUTE_DEVELOPER_TURNSTILE_SECRET` and `NEXT_PUBLIC_ITHUTE_DEVELOPER_TURNSTILE_SITE_KEY`. The service must also enforce appropriate registration rate limits, verification and abuse controls before broad public rollout. Passwords must not appear in logs.

Registration creates **an identity only**. It does not automatically provision a mailbox, verified email status, an OAuth client, or administrative privileges.

## Request an @ithute.co.ls mailbox

A developer may request an Ithute mailbox using the link on the portal. A request is **not** automatic mailbox provisioning. Mailbox eligibility, uniqueness, identity verification, abuse controls, quotas and provisioning approval must be assessed before any address is created. Avoid promising availability of a selected username until it has been provisioned.

If you already have an email address, there is no requirement to obtain an Ithute mailbox before beginning developer onboarding.
