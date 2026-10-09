# Developer API reference

This reference lists confirmed Ithute Auth endpoints. It is not a promise that every Ithute internal or administrative endpoint is publicly available. Use the base URL supplied for your tenant/application by Ithute.

| HTTP | Path | Purpose | Authentication |
| --- | --- | --- | --- |
| GET | `/.well-known/openid-configuration` | Identity service metadata | Public |
| GET | `/.well-known/jwks.json` | Validate signed tokens | Public |
| POST | `/v1/users/register` | Register an identity | Public but must be abuse-protected |
| GET | `/oauth/authorize` | Start PKCE authorization | Browser authorization flow |
| POST | `/oauth/token` | Code exchange / refresh grant | Valid OAuth client and grant |
| GET | `/v1/account/session-status` | Confirm active session and application | Bearer access token |
| POST | `/v1/account/sessions/revoke-current` | Revoke current session | Bearer access token |

## Errors

Expect `400` for invalid authorization requests, `401` for missing/invalid/expired sessions, `403` for insufficient permissions, and `429` where request limiting is deployed. Handle network failure safely and avoid logging bearer tokens.

## Not yet self-service

OAuth application creation, callback changes, activation, Push, DNS, mailbox provisioning, and infrastructure control are not general public developer APIs. Elevated administrators or authorized tenant operators manage these services today. Request access through Ithute rather than reusing platform-owner credentials.
