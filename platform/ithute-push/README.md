# !thute Push

`!thute Push` is the centralized notification-delivery service for applications owned by Ithute Solutions.

The service is designed around one important platform rule:

> Every Ithute product keeps its own business database, while identity is centralized in !thute Auth and device-notification delivery is centralized in !thute Push.

For the current v1 release, Android is the production target. Firebase Cloud Messaging (FCM) is used only as the Android last-mile transport. Firebase does **not** own Ithute identity, user data, product data, notification policy, delivery history or business workflows.

This document is the authoritative implementation/status guide for the current Android-first Push rollout and the Mailbox realtime mail-event integration.

---

## 1. Current project status

### Overall status

The central Push backend is substantially implemented and ready for an Android-first production rollout once the required Firebase project/credentials, server configuration and Android app integration are supplied.

The Mailbox realtime event stream is also implemented in the same release branch and provides WebSocket + Server-Sent Events (SSE) delivery to the webmail UI.

### Status summary

| Area | Status | Notes |
| --- | --- | --- |
| Central !thute Push API | Implemented | FastAPI service with !thute Auth integration |
| Push PostgreSQL database | Implemented | Dedicated `ithute_push` database |
| Device registration | Implemented | Per central user + per product + per installation |
| FCM Android delivery | Implemented server-side | Requires real Firebase credentials and Android client SDK setup |
| Android notification sound/channel support | Implemented server contract | Android app must create matching high-importance channel |
| FCM token refresh support | Implemented API contract | Android app must call registration when token changes |
| Push retries/backoff | Implemented | Worker retries transient provider errors |
| Invalid-token cleanup | Implemented | Invalid/unregistered tokens are deactivated |
| Idempotent notification publishing | Implemented | Uses `Idempotency-Key` + DB uniqueness |
| Provider acceptance reporting | Implemented | `delivered` means provider accepted the message |
| Device receipt acknowledgement | Implemented | Android app posts `received` |
| Notification-open acknowledgement | Implemented | Android app posts `opened` |
| Device inventory | Implemented | Current user/product can list registered devices |
| Production readiness endpoint | Implemented | `/readyz` validates encryption + configured providers |
| Android-first readiness policy | Implemented | `PUSH_REQUIRED_PROVIDERS=fcm` |
| APNs provider code | Present, not current rollout target | Can be enabled later |
| Web Push provider code | Present, not current rollout target | Can be enabled later |
| Webmail Redis event stream | Implemented | Mailbox-isolated Redis Streams |
| Webmail SSE endpoint | Implemented | Replay IDs + heartbeat |
| Webmail WebSocket endpoint | Implemented | Replay cursor + heartbeat |
| Webmail frontend realtime client | Implemented | WebSocket first, SSE fallback |
| External inbound-mail detection | Implemented | Lightweight IMAP mailbox snapshot probe |
| GitHub automated test workflow | Defined | Current GitHub runner/account issue prevents jobs from starting |
| Physical Android FCM test | Not yet possible | Requires Firebase project + real Android app/device |
| Production deployment verification | Not yet complete | Requires server secrets/configuration and live deployment |

---

## 2. Architecture

### Central platform architecture

```text
                    +----------------------+
                    |     !thute Auth      |
                    | central identity     |
                    +----------+-----------+
                               |
                    user/service JWT tokens
                               |
            +------------------+------------------+
            |                                     |
            v                                     v
+-------------------------+            +-------------------------+
| Product application     |            |      !thute Push        |
| LoanHub / Mailbox / POS |            | central delivery API    |
| own product database    |            | own PostgreSQL database |
+-----------+-------------+            +-----------+-------------+
            |                                      |
            | service notification request         | queued delivery
            +-------------------------------------> |
                                                   v
                                         +-------------------+
                                         | Push worker       |
                                         | retry + provider  |
                                         +---------+---------+
                                                   |
                                                   v
                                         +-------------------+
                                         | Firebase FCM      |
                                         | Android transport |
                                         +---------+---------+
                                                   |
                                                   v
                                         +-------------------+
                                         | Android device    |
                                         | app notification  |
                                         +-------------------+
```

### Platform boundary

- Each product owns its own product/business database.
- !thute Auth owns human and service identity.
- !thute Push owns device/provider endpoints, queued notifications, retry attempts and delivery receipts.
- Products never need to call Firebase directly.
- !thute Push never reads LoanHub, Mailbox-DNS, RSL POS or another product database.
- Firebase is only the transport between !thute Push and Android devices.

A device registration is scoped by:

```text
central user (`sub`)
+ product client (`aud` / client id)
+ installation (`device_key`)
```

Therefore a LoanHub service cannot accidentally send to a Mailbox or RSL POS endpoint belonging to the same human user.

---

## 3. What Firebase does and does not do

### Firebase is used for

- Firebase Cloud Messaging (FCM)
- Android registration tokens
- Last-mile delivery from !thute Push to Android

### Firebase is not used for

- authentication
- authorization
- user accounts
- product databases
- Firestore
- Realtime Database
- Firebase Hosting
- Firebase business rules
- notification history
- Ithute service-to-service identity

The final Android path is:

```text
Product backend
    -> !thute Auth service identity
    -> !thute Push API
    -> Push PostgreSQL queue
    -> Push worker
    -> Firebase Cloud Messaging
    -> Android application
```

---

## 4. Authentication model

### User operations

Device registration, device inventory, device revocation and delivery acknowledgement require a valid central !thute Auth user access token.

The Push service validates the token through the central !thute Auth JWKS endpoint.

### Product backend operations

Product backends publish notifications using a central !thute Auth service token containing:

```text
iss=https://auth.ithute.co.ls
aud=ithute-push
token_use=service
azp=<product client id>
scope=push.send
```

`azp` identifies which Ithute product is publishing the notification.

Push deliberately has no second password or authentication system.

---

## 5. Android v1 behavior

Android is the current production target.

The Push worker sends through the Firebase Cloud Messaging HTTP v1 API.

The FCM request includes:

- notification title
- notification body
- Android `HIGH` priority
- remaining TTL at the moment of delivery
- notification sound
- configured Android notification channel ID
- product-defined data
- `route`
- `ithute_message_id`
- `ithute_delivery_id`

The default Android notification channel is:

```text
ithute_default
```

The Android application must create the same channel with `IMPORTANCE_HIGH` and sound enabled.

### Important Android limitation

!thute Push and FCM can request a high-priority, audible user-visible notification, but they must not bypass Android/user controls.

Actual sound/display behavior remains subject to:

- Android notification permission
- channel importance
- channel sound setting
- Do Not Disturb
- user silent settings
- battery/OS policy
- device/vendor policy

---

## 6. Device lifecycle

### Registration

```http
POST /v1/devices
Authorization: Bearer <central-user-access-token>
Content-Type: application/json

{
  "device_key": "<installation-uuid>",
  "platform": "android",
  "provider_endpoint": "<fcm-registration-token>"
}
```

`device_key` must be a random app-installation UUID generated once by the Android app and stored in app-private storage.

Do not use:

- IMEI
- phone number
- Android ID
- SIM identifier
- hardware serial number

### Token changes

FCM tokens are not permanent.

Whenever Firebase calls Android `onNewToken()`, the Android app must call `POST /v1/devices` again using the same installation `device_key` and the new FCM token.

### Account switching

If the same FCM registration token becomes associated with a different user in the same product, !thute Push deactivates the older binding before making the new binding authoritative.

This prevents a shared/reused phone from continuing to receive notifications for the previous signed-in account.

### Device inventory

```http
GET /v1/devices
Authorization: Bearer <central-user-access-token>
```

The response contains only devices owned by that central user in that product.

### Logout/revocation

```http
DELETE /v1/devices/{device_key}
Authorization: Bearer <central-user-access-token>
```

The Android app should normally call this before discarding the user's access token during logout.

---

## 7. Publishing notifications

A product backend obtains an !thute Auth service token and calls:

```http
POST /v1/messages
Authorization: Bearer <service-token>
Idempotency-Key: loan-approved:<domain-event-id>
Content-Type: application/json

{
  "recipient_sub": "00000000-0000-0000-0000-000000000001",
  "title": "Loan approved",
  "body": "Your application has been approved.",
  "route": "/loans/123",
  "sound": "default",
  "data": {
    "loan_id": "123"
  },
  "ttl_seconds": 3600
}
```

### Payload limits

Current API validation includes:

- title: 1–160 characters
- body: 1–500 characters
- route: up to 500 characters
- sound name: up to 64 characters
- data payload: maximum approximately 2 KiB encoded
- TTL: minimum 60 seconds
- TTL: maximum 604800 seconds (7 days)

Sensitive customer/business information should not be placed directly in lock-screen notifications. Prefer minimal notification text and a route/reference, then fetch sensitive data from the product after authenticated app opening.

---

## 8. Idempotency and duplicate protection

Every product backend should send an `Idempotency-Key` for business notifications.

Example:

```text
loan-approved:loan-event-58392
invoice-overdue:invoice-422:2026-09-04
mail-arrived:<stable-mail-event-id>
```

The service stores a request fingerprint together with the key.

Behavior:

- same product + same key + same request -> original message is returned
- same product + same key + different request -> HTTP `409`
- concurrent duplicate requests -> database uniqueness constraint protects the operation

This prevents a product retry, network retry or duplicated business event from producing duplicate push notifications.

---

## 9. Queue and worker behavior

Notification requests are stored before provider delivery.

The worker:

1. selects queued/retry deliveries;
2. locks work rows so parallel workers do not process the same delivery;
3. checks notification expiry;
4. decrypts the provider endpoint;
5. calls the appropriate provider;
6. records provider acceptance/failure;
7. retries transient failures;
8. deactivates only endpoints known to be invalid/unregistered;
9. updates aggregate message status.

Current retry backoff sequence is approximately:

```text
60 seconds
300 seconds
1800 seconds
7200 seconds
```

The worker uses a configurable maximum-attempt count.

### Error classes

The delivery code distinguishes:

- provider not configured
- invalid/unregistered endpoint
- permanent message/provider rejection
- retryable/transient provider failure

This distinction is important because a bad payload or provider configuration must not automatically destroy a valid device registration.

---

## 10. Delivery status semantics

Provider delivery and physical-device acknowledgement are intentionally separate.

### Service/provider status

- `queued` — message waiting for worker processing
- `processing` — one or more deliveries are still active/retrying
- `delivered` — all targeted provider requests were accepted
- `partial` — some deliveries succeeded and some permanently failed
- `failed` — targeted deliveries ended unsuccessfully
- `no_endpoints` — no active device endpoint existed for the user/product
- `expired` — delivery exceeded its Ithute TTL window
- `configuration_error` — required provider configuration prevented delivery

### Device acknowledgement

`delivered` does **not** mean that the phone displayed the notification.

FCM acceptance and physical device/app receipt are different events.

The Android app can acknowledge:

```http
POST /v1/deliveries/{delivery_id}/ack
Authorization: Bearer <central-user-access-token>
Content-Type: application/json

{"state":"received"}
```

When the user opens the notification:

```json
{"state":"opened"}
```

The Push service stores:

- `received_at`
- `opened_at`

The acknowledgement endpoint verifies that the delivery belongs to both the authenticated central user and the current product client.

---

## 11. Push API reference

### Health

```text
GET /healthz
```

Process liveness only.

### Production readiness

```text
GET /readyz
```

Checks:

- endpoint encryption configuration
- configured required providers
- FCM project ID
- FCM service-account file presence
- expected FCM service-account JSON fields

Production Compose uses `/readyz`, not `/healthz`, as the Push API health gate.

### Devices

```text
POST   /v1/devices
GET    /v1/devices
DELETE /v1/devices/{device_key}
```

### Messages

```text
POST /v1/messages
GET  /v1/messages/{message_id}
```

### Delivery acknowledgement

```text
POST /v1/deliveries/{delivery_id}/ack
```

---

## 12. Database ownership

!thute Push owns a separate PostgreSQL database:

```text
ithute_push
```

It does not share the product database with Mailbox, LoanHub or RSL POS.

### Main tables

#### Push endpoints

Stores:

- central Auth user UUID
- product/application ID
- app installation device key
- platform
- provider
- encrypted provider endpoint/token
- provider-endpoint hash
- active state
- last-seen timestamp

#### Messages

Stores:

- source product/client
- recipient central-user UUID
- idempotency key
- request fingerprint
- title/body
- route
- sound
- product data JSON
- aggregate status
- expiry
- creation timestamp

#### Deliveries

Stores:

- message
- endpoint
- delivery status
- attempts
- provider message ID
- last error
- retry time
- provider accepted timestamp
- device received timestamp
- notification opened timestamp

---

## 13. Encryption and secret handling

Provider endpoints such as FCM registration tokens are encrypted at rest using a dedicated Fernet key.

The Fernet key must be supplied through deployment configuration:

```text
ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY
```

Never commit:

- Firebase service-account JSON
- Fernet encryption key
- APNs private key
- VAPID private key
- !thute Auth private signing key
- service client secrets

---

## 14. Production environment values for Android v1

The central platform Compose currently expects values equivalent to:

```env
ITHUTE_PUSH_REQUIRED_PROVIDERS=fcm
ITHUTE_PUSH_FCM_PROJECT_ID=<firebase-project-id>
ITHUTE_PUSH_FCM_ANDROID_CHANNEL_ID=ithute_default
ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY=<fernet-key>
```

The Firebase service account is mounted from:

```text
./platform-secrets/ithute-push/fcm-service-account.json
```

Inside the container it is read from:

```text
/run/secrets/fcm-service-account.json
```

---

## 15. What remains before real Android delivery

The server implementation is present. Real Android delivery still requires external/runtime work.

### Required: Firebase project

Create the Firebase/Google Cloud project used for Android FCM delivery.

### Required: service account

Create/download a service-account JSON authorized to send Firebase Cloud Messaging messages.

Install it on the production server at:

```text
platform-secrets/ithute-push/fcm-service-account.json
```

### Required: production environment

Set:

```text
ITHUTE_PUSH_FCM_PROJECT_ID
ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY
```

### Required: Android application integration

Each Android Ithute application must:

- add Firebase Messaging SDK
- include the Firebase Android application configuration
- request Android 13+ notification permission
- create `ithute_default` as a HIGH-importance channel
- enable sound on that channel
- generate/store app-installation `device_key`
- obtain an FCM registration token
- register/refresh the token with !thute Push
- handle `onNewToken()`
- handle notification route/deep link
- post `received` acknowledgement
- post `opened` acknowledgement
- revoke the binding during logout where appropriate

### Required: product backend integration

Each product that sends notifications must:

- obtain an !thute Auth service token for `ithute-push`
- include scope `push.send`
- call `POST /v1/messages`
- supply a stable `Idempotency-Key`
- send only lock-screen-safe notification content

### Required: production verification

After deployment confirm:

```text
https://push.ithute.co.ls/healthz
https://push.ithute.co.ls/readyz
```

`/readyz` must return HTTP 200 before the Android rollout is considered production-ready.

---

## 16. Android physical-device acceptance test

The Android release is not complete until a real phone passes the following tests.

### Registration

- app installs
- user signs in through !thute Auth
- FCM token is generated
- token is registered with !thute Push
- device appears in `GET /v1/devices`

### Foreground

- app open
- backend publishes notification
- notification/event reaches app as designed
- `received_at` appears

### Background

- app in background
- notification appears promptly
- tapping notification routes correctly
- `opened_at` appears

### Screen locked

- phone locked
- app not active
- high-priority notification arrives
- notification sound follows channel/user settings
- tapping routes to correct authenticated screen

### Doze/idle

- phone left idle long enough to enter power-saving behavior
- high-priority FCM message still arrives within expected Android/FCM behavior

### Token refresh

- new FCM token is generated/refreshed
- app re-registers it
- old binding does not leak notifications

### Logout/account switch

- user A logs out
- binding is deactivated/rebound appropriately
- user A no longer receives user B's notifications

### Retry/idempotency

- same business event is submitted twice with same `Idempotency-Key`
- only one logical notification is created

---

## 17. Mailbox realtime SSE/WebSocket integration

The same release includes the realtime Mailbox event layer.

This functionality is implemented in the Mailbox backend/frontend rather than inside the Push service process, but it is documented here because it forms part of the same notification/realtime platform milestone.

### Why both systems exist

`!thute Push` solves notification delivery when the Android app may be backgrounded or sleeping.

The Mailbox realtime stream solves live updates while a browser/webmail session is open.

They serve different purposes:

```text
Android asleep/background:
Mailbox/Product -> !thute Push -> FCM -> Android

Browser currently open:
Mailbox backend -> Redis Stream -> WebSocket/SSE -> Webmail UI
```

### Event bus

Mailbox events use Redis Streams.

Each mailbox receives its own hashed stream key so the raw mailbox address is not embedded in the Redis event-stream key.

The stream keeps bounded replay history.

### SSE endpoint

```text
GET /api/v1/webmail/events/stream
```

Features:

- existing secure webmail-session cookie authentication
- SSE event IDs
- browser `Last-Event-ID` replay
- heartbeat comments
- Nginx buffering disabled
- long read timeout

### WebSocket endpoint

```text
/api/v1/webmail/events/ws
```

Features:

- existing secure webmail-session cookie authentication
- origin validation
- heartbeat messages
- replay cursor via `last_event_id`
- long-lived Nginx HTTP/1.1 Upgrade configuration

### Browser strategy

The Webmail frontend:

1. tries WebSocket first;
2. falls back to SSE if WebSocket is unavailable;
3. reconnects automatically;
4. remembers the last event ID for replay;
5. refreshes the visible mailbox when `mailbox.changed` arrives;
6. does not force the user out of a message currently being read;
7. applies the pending refresh when the user returns to the message list.

### Event sources

Mailbox events are produced from two paths.

#### Immediate webmail mutations

Successful actions such as:

- send
- move
- archive
- delete
- flags/read state
- draft changes

publish a mailbox event immediately.

#### External mailbox changes

Incoming messages delivered through the mail stack or changes made by another mail client do not pass through the Webmail HTTP mutation endpoints.

To catch those changes, the realtime service performs a lightweight IMAP mailbox snapshot check using folder message/unseen counts.

A Redis probe lock ensures that multiple browser tabs do not each perform the same IMAP probe simultaneously.

When the snapshot changes, `mailbox.changed` is emitted.

---

## 18. Realtime Mailbox deployment requirements

Realtime Webmail requires:

- Redis running and reachable by the backend
- Mailbox backend deployed with the new event router/service
- Nginx deployed with the new SSE/WebSocket locations
- Webmail frontend deployed with `MailRealtime`
- existing webmail session-cookie configuration working
- IMAP connectivity from the backend

No additional user login/token system is introduced.

---

## 19. Important design decisions

### One central Push service

All Ithute products share the delivery engine, but device registration and sending remain product-isolated.

### Product databases remain separate

Push never becomes the source of truth for loan, mail, POS or other business data.

### Firebase is replaceable transport infrastructure

The public product contract is the !thute Push API, not Firebase APIs.

This keeps product code independent from provider-specific server APIs.

### Provider acceptance is not device receipt

Reporting deliberately separates provider acceptance from authenticated application receipt/open actions.

### Realtime web events are not a replacement for Android push

SSE/WebSocket require an active client connection. FCM is the correct transport for Android background/sleep delivery.

---

## 20. Local Push development

From `platform/ithute-push`:

```bash
cp .env.example .env
```

Set a valid Fernet key and development configuration.

Then:

```bash
docker compose up --build
```

The local compose stack contains:

- PostgreSQL
- Push API
- Push worker

The local API is exposed on:

```text
http://localhost:8089
```

### Database migrations

The service entrypoint applies Alembic migrations before starting the API/worker environment according to the container startup contract.

The current reliability migration adds:

- message idempotency key
- message request fingerprint
- unique per-product idempotency constraint
- `received_at`
- `opened_at`

---

## 21. Test commands

The Push GitHub workflow is designed to execute the following non-provider tests:

```bash
cd platform/ithute-push
python3 -m pip install --disable-pip-version-check -r requirements.txt
python3 -m compileall -q app alembic tests
python3 -m pytest -q
```

These tests do **not** send real FCM messages and therefore do not require Firebase billing or a physical device.

The contract tests cover areas including:

- Android/FCM provider mapping
- endpoint encryption round-trip
- deterministic endpoint hashing
- Android-first provider readiness
- optional provider expansion
- idempotency fingerprint stability
- delivery acknowledgement schema
- remaining-TTL calculation

Mailbox event tests cover:

- mailbox stream-key stability/isolation
- raw mailbox address not exposed in the stream key
- SSE frame ID/type/payload structure
- replay cursor validation

---

## 22. Current GitHub Actions condition

At the time this README was updated, the relevant PR workflows were being created by GitHub but the jobs were not being assigned to a runner.

Observed behavior:

```text
runner_id: 0
runner_name: empty
steps: empty
```

Therefore GitHub displayed the workflows as failed even though no checkout, dependency install, compilation or pytest step actually ran.

This is an Actions runner/account/infrastructure condition, not a test assertion failure.

The release should still be validated with all available local/static checks before merge. Once GitHub Actions is available again, the normal CI workflow must also be allowed to execute.

---

## 23. Merge readiness checklist

Before merging the Android-first Push/realtime release:

- [x] Central Push architecture implemented
- [x] !thute Auth user/service verification implemented
- [x] Separate Push PostgreSQL database retained
- [x] Android FCM HTTP v1 provider implemented
- [x] HIGH-priority Android provider payload implemented
- [x] Android notification channel ID configurable
- [x] TTL uses remaining lifetime rather than original lifetime
- [x] Provider errors separated into invalid/configuration/permanent/retryable categories
- [x] Invalid endpoints deactivate safely
- [x] Valid endpoints are not disabled for unrelated message failures
- [x] Idempotency implemented with concurrency-safe DB uniqueness
- [x] Device inventory implemented
- [x] Receipt/open acknowledgements implemented
- [x] Database migration added
- [x] `/readyz` validates Android provider configuration
- [x] Production Compose gates Push on `/readyz`
- [x] Android integration contract documented
- [x] Redis mail-event stream implemented
- [x] SSE endpoint implemented
- [x] WebSocket endpoint implemented
- [x] Webmail browser client implemented
- [x] WebSocket -> SSE fallback implemented
- [x] Event replay implemented
- [x] IMAP external-mail detection implemented
- [x] Multi-tab IMAP probe coordination implemented
- [x] Nginx SSE/WebSocket support implemented
- [x] Non-provider test workflow defined
- [ ] GitHub-hosted runner successfully executes CI
- [ ] Firebase project created
- [ ] Production FCM service account installed
- [ ] Production Push Fernet key configured
- [ ] Android application Firebase Messaging SDK integrated
- [ ] Real Android device test completed
- [ ] Production `/readyz` verified HTTP 200

The unchecked Firebase/Android/deployment items are **post-code external rollout requirements** and do not require committing provider secrets to Git.

---

## 24. What is intentionally left for later

The current target is Android only.

The following can be activated/expanded later without redesigning the central architecture:

### Apple

- production APNs credentials
- iOS app registration
- iOS notification handling
- Apple device tests

### Browser background push

- production VAPID credentials
- Web Push subscription UI
- service worker
- background browser notification handling

### Operations enhancements

Potential later improvements include:

- Prometheus metrics dedicated to Push queue/provider latency
- admin delivery dashboard
- delivery requeue tooling
- stale inactive-endpoint retention cleanup
- notification-category preferences
- product quotas/rate limits
- scheduled notification support
- dead-letter queue/reporting
- key-versioned Fernet rotation
- provider Retry-After-aware backoff/jitter

These are useful platform evolutions but are not required for the first Android FCM delivery path.

---

## 25. Definition of Android v1 complete

The Android-first milestone is fully complete only when all of the following are true:

1. code in this release is merged;
2. Push migrations are applied;
3. Firebase project exists;
4. FCM service-account credential is installed securely;
5. Push Fernet key is configured;
6. `push.ithute.co.ls` is deployed and routed through HTTPS;
7. `/readyz` returns HTTP 200;
8. Android application contains Firebase Messaging integration;
9. Android application creates `ithute_default` with HIGH importance and sound;
10. device registration works with central !thute Auth;
11. a product backend publishes through a service token;
12. real phone receives the notification in foreground/background/locked conditions;
13. token refresh works;
14. logout/account switching cannot leak notifications;
15. `received_at` and `opened_at` can be observed in delivery reporting.

Until steps 3–15 are verified in the live environment, the repository implementation should be described as **code-complete for Android-first integration, pending provider/runtime/mobile acceptance** rather than claiming that production push delivery has already been proven.

---

## 26. Related files

### Push service

```text
platform/ithute-push/
├── README.md
├── ANDROID-FCM.md
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── entrypoint.sh
├── alembic.ini
├── alembic/
│   └── versions/
│       ├── 0001_push_delivery.py
│       └── 0002_push_reliability.py
├── app/
│   ├── auth.py
│   ├── config.py
│   ├── crypto.py
│   ├── db.py
│   ├── main.py
│   ├── models.py
│   ├── providers.py
│   ├── schemas.py
│   └── worker.py
└── tests/
    └── test_contract.py
```

### Platform deployment

```text
docker-compose.ithute-platform.yml
infrastructure/nginx/default.conf
.github/workflows/ithute-push.yml
.github/workflows/ithute-platform-production.yml
```

### Mailbox realtime implementation

```text
apps/backend/app/api/v1/webmail_events.py
apps/backend/app/services/mail_events.py
apps/backend/app/main.py
apps/backend/tests/test_webmail_events.py
apps/frontend/app/webmail/mail-realtime.tsx
apps/frontend/app/webmail/layout.tsx
infrastructure/nginx/default.conf
```

---

## 27. Final current-state summary

As of this release branch:

**Implemented in code**

- centralized !thute Push service
- Android-first FCM backend delivery path
- secure per-product device registration
- encrypted FCM token storage
- retry/error handling
- duplicate-notification protection
- delivery reporting and app acknowledgements
- Android production-readiness checks
- Mailbox Redis/SSE/WebSocket realtime updates
- Webmail realtime browser integration

**Still external / runtime / mobile**

- create Firebase project
- install FCM service account
- configure production Fernet key
- deploy/restart Push API + worker + migration
- integrate Firebase Messaging in Android application
- run physical Android delivery tests
- verify live production HTTPS/readiness

The architecture should not be rebuilt to achieve Android push. The remaining work is to connect real Firebase credentials and the Android application to the central service that is now present.
