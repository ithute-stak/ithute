import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.config import Settings
from app.crypto import EndpointCipher, endpoint_hash
from app.main import clean_idempotency_key, message_fingerprint, provider_for
from app.policy import python_transport_order
from app.providers import _ttl_seconds
from app.schemas import DelegatedMessageRequest, DeliveryAckRequest, MessageRequest


def _key() -> str:
    return base64.urlsafe_b64encode(b"x" * 32).decode("ascii")


def _write_fcm_credentials(path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "ithute-prod",
                "client_email": "push@ithute-prod.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )


def test_provider_mapping() -> None:
    assert provider_for("android") == "fcm"
    assert provider_for("android", "ithute") == "ithute"
    assert provider_for("android", "fcm") == "fcm"
    assert provider_for("ios") == "apns"
    assert provider_for("web") == "webpush"




def test_android_transport_policy_prefers_ithute_before_fcm() -> None:
    assert python_transport_order("android", {"ithute", "fcm"}) == ["ithute", "fcm"]
    assert python_transport_order("android", {"fcm"}) == ["fcm"]


def test_online_transport_policy_prefers_realtime() -> None:
    assert python_transport_order("android", {"ithute", "fcm"}, online=True) == [
        "realtime",
        "ithute",
        "fcm",
    ]

def test_endpoint_encryption_roundtrip() -> None:
    cipher = EndpointCipher(_key())
    encrypted = cipher.encrypt("provider-secret-token")
    assert "provider-secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == "provider-secret-token"
    assert endpoint_hash("provider-secret-token") == endpoint_hash("provider-secret-token")


def test_sensitive_data_size_is_bounded() -> None:
    MessageRequest(recipient_sub="00000000-0000-0000-0000-000000000001", title="Hello", body="World", data={"id": "123"})


def test_android_fcm_is_default_readiness_baseline(tmp_path) -> None:
    fcm = tmp_path / "fcm.json"
    apns = tmp_path / "apns.p8"
    vapid = tmp_path / "vapid.pem"
    settings = Settings(
        database_url="sqlite://",
        endpoint_encryption_key=_key(),
        fcm_project_id="ithute-prod",
        fcm_credentials_file=str(fcm),
        apns_team_id="TEAM123",
        apns_key_id="KEY123",
        apns_bundle_id="ls.co.ithute.app",
        apns_private_key_file=str(apns),
        vapid_public_key="public-key",
        vapid_private_key_file=str(vapid),
    )
    assert settings.required_provider_set == {"fcm"}
    assert settings.provider_readiness() == {"ithute": False, "fcm": False, "apns": False, "webpush": False}
    assert settings.missing_required_providers() == ["fcm"]

    fcm.write_text("{}", encoding="utf-8")
    assert settings.provider_readiness()["fcm"] is False
    _write_fcm_credentials(fcm)
    assert settings.provider_readiness()["fcm"] is True
    assert settings.missing_required_providers() == []


def test_ithute_owned_transport_can_be_required_without_fcm() -> None:
    settings = Settings(
        database_url="sqlite://",
        endpoint_encryption_key=_key(),
        required_providers="ithute",
        ithute_gateway_url="http://ithute-go-worker:8080",
        ithute_gateway_token="gateway-secret",
    )
    assert settings.required_provider_set == {"ithute"}
    assert settings.provider_readiness()["ithute"] is True
    assert settings.missing_required_providers() == []


def test_android_can_register_both_ithute_and_fcm_transports() -> None:
    assert provider_for("android", "ithute") == "ithute"
    assert provider_for("android", "fcm") == "fcm"


def test_required_providers_can_expand_after_android_rollout(tmp_path) -> None:
    fcm = tmp_path / "fcm.json"
    _write_fcm_credentials(fcm)
    settings = Settings(
        database_url="sqlite://",
        endpoint_encryption_key=_key(),
        required_providers="fcm,apns",
        fcm_project_id="ithute-prod",
        fcm_credentials_file=str(fcm),
    )
    assert settings.required_provider_set == {"fcm", "apns"}
    assert settings.missing_required_providers() == ["apns"]


def test_idempotency_fingerprint_is_stable() -> None:
    payload = MessageRequest(
        recipient_sub="00000000-0000-0000-0000-000000000001",
        title="Approved",
        body="Your application was approved",
        route="/loans/123",
        data={"loan_id": "123"},
    )
    assert message_fingerprint(payload) == message_fingerprint(payload)
    assert clean_idempotency_key(" approval:123 ") == "approval:123"


def test_delivery_ack_contract_accepts_received_and_opened() -> None:
    assert DeliveryAckRequest(state="received").state == "received"
    assert DeliveryAckRequest(state="opened").state == "opened"


def test_provider_ttl_uses_remaining_lifetime() -> None:
    message = SimpleNamespace(expires_at=datetime.now(timezone.utc) + timedelta(seconds=120))
    ttl = _ttl_seconds(message)
    assert 115 <= ttl <= 120


def test_default_delegated_platform_senders_are_realtime_and_notification() -> None:
    settings = Settings(database_url="sqlite://", endpoint_encryption_key=_key())
    assert {"ithute-realtime", "ithute-notification"} <= settings.service_clients
    assert settings.delegated_clients == {"ithute-realtime", "ithute-notification"}
    assert "ithute-realtime" not in settings.user_clients
    assert "ithute-notification" not in settings.user_clients


def test_delegated_message_carries_original_product_namespace() -> None:
    payload = DelegatedMessageRequest(
        source_client_id="loanhub",
        recipient_sub="00000000-0000-0000-0000-000000000001",
        title="New message",
        body="A new chat message is waiting",
        route="/chat/123",
        data={"type": "chat.message"},
    )
    assert payload.source_client_id == "loanhub"
