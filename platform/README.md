# !thute Platform Services

The `platform/` directory contains shared infrastructure used by every Ithute product. These services are not product features and do not belong to LoanHub, Mailbox DNS, Ithute Pay, RSL POS or any other individual application.

## Central services

| Service | Public origin | Responsibility |
| --- | --- | --- |
| `!thute Auth` | `https://auth.ithute.co.ls` | identity, SSO, MFA/passkeys, sessions and signed user/service tokens |
| `!thute Push` | `https://push.ithute.co.ls` | registered device endpoints, background delivery, retries and provider credentials |
| `!thute Realtime` | `https://realtime.ithute.co.ls` | authenticated WebSockets, presence, chat conversations/messages, read state and realtime fan-out |

## Boundary rule

A product owns its business data and authorization. Platform services own only their platform domain. Products never read platform databases directly and never read another product database.

The intended realtime path is:

```text
Product UI
   |
   | central user access token
   v
!thute Realtime <----> Redis fan-out/presence
   |       |
   |       +----> dedicated Realtime PostgreSQL history
   |
   +----> !thute Push ----> FCM / APNs / Web Push when recipient is offline
              ^
              |
         short-lived service JWT from !thute Auth
```

Identity is always the immutable Auth `sub`. Realtime uses the token audience as the product namespace, so the same person can participate in LoanHub chat and Mailbox chat without either product seeing the other's conversations or device endpoints.

Platform service-to-service calls use short-lived Auth JWTs and explicit scopes. Long-lived product/provider secrets remain runtime-only.
