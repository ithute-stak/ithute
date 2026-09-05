# !thute Realtime v2

`!thute Realtime` is the shared realtime backbone for Ithute products. It is a platform service, not a product database and not a super-admin system.

## Security boundary

- Human identity comes only from `!thute Auth` RS256 access tokens.
- The token audience is the product namespace (`loanhub`, `ithute-pay`, `mailbox-dns`, etc.).
- Conversations, events, presence and broadcasts are always filtered by that namespace.
- Product databases remain authoritative for companies, branches, roles, loans, merchants, classes and other business membership. A product resolves the recipient `sub` values before asking Realtime to broadcast.
- Product backends use `aud=ithute-realtime` service tokens and scopes such as `realtime.manage`, `realtime.publish`, `realtime.broadcast` and `realtime.metrics`.
- `REALTIME_DISABLED_CLIENTS` is an operations-controlled emergency kill switch.

## WebSocket

Connect to:

```text
wss://realtime.ithute.co.ls/v1/ws
```

The first frame authenticates the connection without putting a token in the URL:

```json
{"type":"auth","access_token":"<central token>","device_key":"installation-uuid","after":"<optional replay cursor>"}
```

The socket supports multiple devices per user, connection limits, heartbeat expiry, slow-client send timeouts and Redis fan-out across replicas. Persistent commands remain REST operations; the socket carries events, heartbeats and acknowledgements.

## Durable replay

Every durable chat/system/broadcast event receives a stable `event_id`, ordered `cursor`, version, TTL and product namespace. A reconnecting client can use the `after` cursor in its auth frame or call:

```text
GET /v1/events/replay?after=<cursor>
```

Events can be acknowledged as `received` or `opened`. Message receipts separately support `accepted`, `delivered` and `read` state.

## Chat and rooms

Conversation kinds:

- `direct`
- `group`
- `channel`
- `system`

Channels/system rooms use a product-scoped `room_key`. Chat supports replies, forwarding references, mentions, secure attachment references, edits, soft deletion, reactions, pins, delivery/read receipts, typing, recording/uploading/viewing activity and presence/last-seen state.

Attachments are references only. Realtime does not become a file store. Remote references must use HTTPS; product-relative routes are also allowed.

## Product events and broadcasting

Product backends publish to:

```text
POST /v1/platform/events
```

Event families are namespaced, for example:

```text
chat.*
presence.*
notification.*
broadcast.*
system.*
payment.*
loan.*
mail.*
task.*
device.*
security.*
```

The same API supports live dashboards, job progress, secure user notifications and role/company/branch broadcasts after the product resolves recipients. Important controls include:

- explicit recipient `sub` values
- `audience_label` for audit/display metadata
- `priority`: low / normal / high / critical
- TTL/expiry
- scheduled `deliver_at`
- idempotency keys
- optional offline Push fallback
- connected-user broadcasts
- event versioning

## Reliability

Durable events are written to PostgreSQL before publication. Redis is used for fan-out/presence, not as the source of truth. The event worker processes scheduled and retry events. After the configured attempt limit, an event enters `dead_letter` instead of being silently discarded.

Product-scoped metrics and audit history are exposed through service-token endpoints. Rate limits apply to user message/activity traffic and service event publication.

## Push

If a durable event requests Push and a recipient is offline, Realtime delegates through `!thute Push` using a short-lived central service token. Realtime never stores FCM/APNs/Web-Push credentials.

## Examples

Payment update:

```json
{
  "event_type": "payment.updated",
  "version": 1,
  "recipient_subs": ["00000000-0000-0000-0000-000000000001"],
  "priority": "high",
  "push": true,
  "ttl_seconds": 3600,
  "data": {"payment_id": "pay_456", "status": "completed"},
  "idempotency_key": "payment:pay_456:completed"
}
```

Company announcement after the product resolves the company members:

```json
{
  "event_type": "broadcast.message",
  "recipient_subs": ["<user-sub-1>", "<user-sub-2>"],
  "audience_label": "company:acme",
  "title": "Maintenance",
  "body": "The service will be unavailable at 22:00.",
  "priority": "high",
  "push": true,
  "idempotency_key": "maintenance:2026-09-05"
}
```

Job progress:

```json
{
  "event_type": "task.progress",
  "recipient_subs": ["<user-sub>"],
  "data": {"job_id": "report-123", "progress": 70, "state": "running"},
  "ttl_seconds": 1800
}
```
