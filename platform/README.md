# !thute Platform Services

The `platform/` directory contains services owned and deployed **only by the standalone Ithute project**. Auth, Push and Realtime may expose public integration APIs, but no other project shares their Docker containers, images, networks, volumes or databases.

## Ithute-owned services

| Service | Public origin | Responsibility |
| --- | --- | --- |
| `!thute Auth` | `https://auth.ithute.co.ls` | identity, SSO, MFA/passkeys, sessions and signed user/service tokens |
| `!thute Push` | `https://push.ithute.co.ls` | registered device endpoints, background delivery, retries and provider credentials |
| `!thute Realtime` | `https://realtime.ithute.co.ls` | authenticated WebSockets, presence, chat conversations/messages, read state and realtime fan-out |

## Hard deployment boundary

The production Compose project is named `ithute` and creates only Ithute-owned resources. It declares no external Docker network or external named volume. LoanHub, NBros/BuildTrack, Tutor, Pay, Mail and future products must run in their own Compose projects with their own images, networks, volumes and databases.

If an external product is later authorized to use an Ithute platform API, it integrates over the public HTTPS/WSS contract. It does **not** join the Ithute Docker network and does not read an Ithute platform database directly.

The internal Ithute service path is:

```text
Ithute Auth
   |
   +----> Ithute Push ----> optional FCM / APNs / Web Push provider
   |
   +----> Ithute Realtime <----> Ithute Redis
                     |
                     +----> dedicated Ithute Realtime PostgreSQL
```

Identity is the immutable Auth `sub`. Service-to-service calls use short-lived signed Auth JWTs and explicit scopes. Long-lived database, signing, encryption and provider secrets are runtime-only and are generated or installed only on the Ithute VPS deployment.
