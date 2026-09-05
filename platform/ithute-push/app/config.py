import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_jwks_url: str = "https://auth.ithute.co.ls/.well-known/jwks.json"
    allowed_user_clients: str = "loanhub,rsl-pos,mailbox-dns,ithute-account,ithute-tutor,ithute-pay"
    allowed_service_clients: str = "loanhub,rsl-pos,mailbox-dns,ithute-account,ithute-tutor,ithute-pay,ithute-realtime"
    delegated_service_clients: str = "ithute-realtime"
    allowed_admin_clients: str = "mailbox-dns"
    auth_clock_skew_seconds: int = 30
    auth_max_push_access_seconds: int = 600
    auth_max_service_token_seconds: int = 600
    auth_max_admin_token_seconds: int = 180
    endpoint_encryption_key: str
    worker_poll_seconds: float = 2.0
    max_attempts: int = 4

    # Android/FCM is the v1 production baseline. APNs and Web Push remain
    # implemented providers, but they do not block readiness until explicitly
    # added to PUSH_REQUIRED_PROVIDERS.
    required_providers: str = "fcm"

    fcm_project_id: str | None = None
    fcm_credentials_file: str = "/run/secrets/fcm-service-account.json"
    fcm_android_channel_id: str = "ithute_default"

    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_bundle_id: str | None = None
    apns_private_key_file: str = "/run/secrets/apns-private-key.p8"
    apns_use_sandbox: bool = False

    vapid_subject: str = "mailto:admin@ithute.co.ls"
    vapid_public_key: str | None = None
    vapid_private_key_file: str = "/run/secrets/vapid-private-key.pem"

    model_config = SettingsConfigDict(env_prefix="PUSH_", case_sensitive=False)

    @property
    def user_clients(self) -> set[str]:
        return {item.strip() for item in self.allowed_user_clients.split(",") if item.strip()}

    @property
    def service_clients(self) -> set[str]:
        return {item.strip() for item in self.allowed_service_clients.split(",") if item.strip()}

    @property
    def delegated_clients(self) -> set[str]:
        return {item.strip() for item in self.delegated_service_clients.split(",") if item.strip()}

    @property
    def admin_clients(self) -> set[str]:
        return {item.strip() for item in self.allowed_admin_clients.split(",") if item.strip()}

    @property
    def required_provider_set(self) -> set[str]:
        providers = {item.strip().lower() for item in self.required_providers.split(",") if item.strip()}
        unknown = providers - {"fcm", "apns", "webpush"}
        if unknown:
            raise ValueError(f"unsupported required providers: {', '.join(sorted(unknown))}")
        return providers

    def fcm_ready(self) -> bool:
        if not self.fcm_project_id:
            return False
        path = Path(self.fcm_credentials_file)
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        return bool(
            payload.get("client_email")
            and payload.get("private_key")
            and payload.get("token_uri")
        )

    def provider_readiness(self) -> dict[str, bool]:
        return {
            "fcm": self.fcm_ready(),
            "apns": bool(
                self.apns_team_id
                and self.apns_key_id
                and self.apns_bundle_id
                and Path(self.apns_private_key_file).is_file()
            ),
            "webpush": bool(self.vapid_public_key and Path(self.vapid_private_key_file).is_file()),
        }

    def missing_required_providers(self) -> list[str]:
        readiness = self.provider_readiness()
        return sorted(provider for provider in self.required_provider_set if not readiness[provider])

    def read_secret_file(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
