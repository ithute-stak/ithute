# !thute Realtime

`!thute Realtime` is the centralized WebSocket, realtime-event and chat engine for the Ithute platform. It is a platform service beside `!thute Auth` and `!thute Push`; it is not owned by LoanHub, Mailbox, Ithute Pay or any other product.

## Platform rule

- `!thute Auth` owns identity and signs user/service JWTs.
- `!thute Realtime` owns conversations, memberships, chat messages, read state, presence and realtime fan-out.
- `!thute Push` owns device endpoints and last-mile background notifications.
- Every product keeps its own business database and never reads the Realtime database directly.
- Products integrate through signed HTTP and WebSocket contracts.

Public origin:

```text
https://realtime.ithute.co.ls
wss://realtime.ithute.co.ls/v1/ws
```

## Security model

Human connections use the normal central user token already issued for the product. The token `aud` identifies the product namespace, for example `loanhub`, `mailbox-dns`, `rsl-pos` or `ithute-pay`. Realtime verifies the RS256 signature against the Auth JWKS, exact issuer, expiry, `token_use=access`, and an approved product audience.

Product backends use short-lived Auth service tokens:

```text
iss=https://auth.ithute.co.ls
aud=ithute-realtime
token_use=service
azp=<product-client-id>
scope=realtime.manage realtime.publish
```

No product can create or publish into another product's namespace because `azp` becomes the authoritative application ID.

## WebSocket authentication

Access tokens are deliberately not placed in the WebSocket query string. A client connects to `/v1/ws` and the first frame must be:

```json
{"type":"auth","access_token":"<central-user-access-token>"}
```

The server replies with `ready`. Clients then send periodic `{ "type": "ping" }` frames to renew distributed Redis presence and receive `pong`.

Chat commands use authenticated REST endpoints while the WebSocket carries realtime events. This keeps authorization, idempotency and validation explicit while preserving instant delivery.

## Chat API

User endpoints:

```text
GET  /v1/conversations
POST /v1/conversations
GET  /v1/conversations/{conversation_id}/messages
POST /v1/conversations/{conversation_id}/messages
POST /v1/conversations/{conversation_id}/read
POST /v1/conversations/{conversation_id}/typing
WS   /v1/ws
```

Product service endpoints:

```text
POST /v1/platform/conversations               scope=realtime.manage
POST /v1/platform/conversations/{id}/events   scope=realtime.publish
```

Conversation membership is always stored by immutable central Auth `sub`; email and phone are never used as cross-product identity keys.

## Redis and horizontal scale

Each Realtime replica keeps only its local WebSocket objects. Redis Pub/Sub is the shared fan-out bus, so a message accepted by one replica reaches users connected to any other replica. Redis also stores short-lived per-connection presence keys.

Persistent conversation and message history is stored in the dedicated `ithute_realtime` PostgreSQL database.

## Push fallback

When a recipient has no active WebSocket presence, Realtime obtains a short-lived Auth service token as platform client `ithute-realtime` with `aud=ithute-push` and `scope=push.send.delegated`.

It then asks `!thute Push` to send on behalf of the original product namespace. Push still targets only device endpoints registered for that product, so a LoanHub chat notification cannot leak to the same user's Mailbox installation.

Realtime never stores FCM/APNs/Web-Push credentials.

## Client event examples

Persisted message:

```json
{
  "type": "chat.message",
  "application_id": "loanhub",
  "conversation_id": "...",
  "message": {
    "id": "...",
    "sender_sub": "...",
    "message_type": "text",
    "body": "Hello"
  }
}
```

Read receipt:

```json
{
  "type": "chat.read",
  "conversation_id": "...",
  "reader_sub": "...",
  "message_id": "..."
}
```

Typing indicators are ephemeral and are not stored.

## Data isolation

The central chat database contains only messaging-domain records: product namespace, central user IDs, conversation membership, message content/data and read state. It does not copy loans, payments, mailboxes, POS sales or other product business records.

Sensitive business payloads should remain in the source product. Prefer references/routes in chat event data and fetch protected business details from the product API after authentication.
