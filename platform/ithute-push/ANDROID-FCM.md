# !thute Push — Android / FCM integration

!thute Push owns notification policy, queueing, retries, receipts and product isolation. Firebase Cloud Messaging (FCM) is only the Android last-mile transport.

## Production server setup

1. Create one Firebase project for Ithute Android push delivery (or a deliberate project per environment).
2. Obtain a Google service-account JSON with permission to send Firebase Cloud Messaging messages.
3. Install it on the server as `platform-secrets/ithute-push/fcm-service-account.json` with restrictive filesystem permissions. Never commit it.
4. Set:

```env
ITHUTE_PUSH_REQUIRED_PROVIDERS=fcm
ITHUTE_PUSH_FCM_PROJECT_ID=<firebase-project-id>
ITHUTE_PUSH_FCM_ANDROID_CHANNEL_ID=ithute_default
ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY=<fernet-key>
```

5. Run the push database migrations and require `GET https://push.ithute.co.ls/readyz` to return `200` before exposing the service.

APNs and Web Push remain optional and do not block Android-only readiness.

## Android application setup

The Android application needs the Firebase Messaging SDK only. Ithute Auth remains the identity provider and the product keeps its own product database.

The app must:

- request Android 13+ notification permission;
- create a `HIGH` importance notification channel named `ithute_default` with sound enabled;
- obtain and refresh its FCM registration token;
- keep a random, app-scoped installation UUID as `device_key`;
- register the FCM token with !thute Push after the user authenticates;
- unregister/deactivate the device during logout when appropriate;
- acknowledge `received` and `opened` delivery states;
- route a tapped notification using the `route` data field.

Do not use an IMEI, phone number, Android ID or other hardware identifier as `device_key`. Generate a UUID once per app installation and store it in app-private storage.

### Register or refresh a device

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

Registration is idempotent for `(central user, product client, device_key)`. If the same FCM token moves to a different signed-in account for the same product, the old binding is deactivated so notifications cannot leak to the previous user.

### Send from a product backend

Product backends obtain an !thute Auth service token with:

- audience `ithute-push`;
- scope `push.send`;
- `azp` equal to the product client id.

Then send:

```http
POST /v1/messages
Authorization: Bearer <service-token>
Idempotency-Key: loan-approved:<domain-event-id>
Content-Type: application/json

{
  "recipient_sub": "<central-auth-user-uuid>",
  "title": "Loan approved",
  "body": "Your application has been approved.",
  "route": "/loans/123",
  "sound": "default",
  "data": {"loan_id": "123"},
  "ttl_seconds": 3600
}
```

Always send an `Idempotency-Key` for business events. Retrying the same request returns the original message rather than notifying the user twice. Reusing the key with different content returns HTTP `409`.

!thute Push selects only endpoints registered by that same product client. A LoanHub service token cannot send to an RSL POS endpoint even when both belong to the same central user.

### Delivery acknowledgement

The FCM data payload contains:

- `ithute_message_id`;
- `ithute_delivery_id`;
- `route` when supplied;
- product `data` values.

After the Android app receives the notification, call:

```http
POST /v1/deliveries/<ithute_delivery_id>/ack
Authorization: Bearer <central-user-access-token>
Content-Type: application/json

{"state":"received"}
```

When the user taps/opens it, call the same endpoint with:

```json
{"state":"opened"}
```

The acknowledgement endpoint verifies that the delivery belongs to the authenticated central user and product client.

## Android notification channel

Create the channel before a notification is expected. The channel id must match `PUSH_FCM_ANDROID_CHANNEL_ID`.

```kotlin
val channel = NotificationChannel(
    "ithute_default",
    "Ithute notifications",
    NotificationManager.IMPORTANCE_HIGH
).apply {
    description = "Important notifications from Ithute applications"
    enableVibration(true)
}
getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
```

Android users can change channel sound, importance, Do Not Disturb and notification permission. Neither FCM nor !thute Push should attempt to bypass those user/OS controls.

## FCM token refresh

`FirebaseMessagingService.onNewToken()` must re-register the new token with !thute Push. FCM tokens are not permanent. !thute Push encrypts provider endpoints at rest and hashes them only for safe token-binding comparison.

## Logout

On logout, deactivate the current installation binding:

```http
DELETE /v1/devices/<device_key>
Authorization: Bearer <central-user-access-token>
```

Perform this before discarding the access token. A later successful login/registration reactivates the device binding for the current user.

## Operational meaning of status

`delivered` means FCM accepted the message. It does not by itself prove the device displayed it. `received_at` and `opened_at` are populated only from authenticated app acknowledgements. This distinction is intentional and should be preserved in reporting.
