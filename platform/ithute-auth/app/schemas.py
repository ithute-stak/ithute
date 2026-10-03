from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=128)

    @model_validator(mode="after")
    def identity_required(self) -> "RegisterRequest":
        if not self.email and not self.phone:
            raise ValueError("email or phone is required")
        return self


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    client_id: str = Field(min_length=1, max_length=120)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)
    client_id: str = Field(min_length=1, max_length=120)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class ServiceTokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=120)
    client_secret: str = Field(min_length=24, max_length=512)
    audience: str = Field(
        default="ithute-push",
        pattern=r"^(ithute-push|ithute-realtime|ithute-auth|ithute-mail|business-digital-address)$",
    )
    scope: str = Field(
        default="push.send",
        pattern=(
            r"^(?:push\.send|realtime\.(?:publish|manage|metrics|broadcast)|identity\.invite|"
            r"mailbox\.create|mail\.send|mail\.forward|business\.register|official-message\.send)"
            r"(?: (?:push\.send|realtime\.(?:publish|manage|metrics|broadcast)|identity\.invite|"
            r"mailbox\.create|mail\.send|mail\.forward|business\.register|official-message\.send))*$"
        ),
    )

    @model_validator(mode="after")
    def enforce_managed_service_permissions(self) -> "ServiceTokenRequest":
        requested = frozenset(self.scope.split())
        if self.client_id == "business-digital-address":
            allowed = {
                "ithute-auth": frozenset({"identity.invite"}),
                "ithute-mail": frozenset({"mailbox.create", "mail.send", "mail.forward"}),
            }
            audience_scopes = allowed.get(self.audience)
            if audience_scopes is None or not requested or not requested.issubset(audience_scopes):
                raise ValueError("service client is not authorized for the requested audience or scope")
        elif self.client_id == "trade-simulator":
            if self.audience != "business-digital-address" or requested != {"business.register"}:
                raise ValueError("service client is not authorized for the requested audience or scope")
        elif self.client_id == "rsl-simulator":
            if self.audience != "business-digital-address" or requested != {"official-message.send"}:
                raise ValueError("service client is not authorized for the requested audience or scope")
        elif self.audience not in {"ithute-push", "ithute-realtime"}:
            # Existing Push/Realtime service clients keep their established
            # behavior, but no unrecognized client may mint BDA/Auth/Mail scopes.
            raise ValueError("service client is not authorized for the requested audience")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    id_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int


class ServiceTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str


class PushTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str = "push.device"


class UserResponse(BaseModel):
    sub: str
    email: str | None
    phone: str | None
    display_name: str
    email_verified: bool
    phone_verified: bool
    mfa_enabled: bool = False


class DeviceRequest(BaseModel):
    device_key: str = Field(min_length=8, max_length=200)
    platform: str = Field(pattern="^(android|ios|web|desktop)$")
    label: str | None = Field(default=None, max_length=160)


class DeviceResponse(BaseModel):
    id: str | None = None
    device_key: str
    platform: str
    label: str | None
    active: bool
    trusted: bool = False
    trusted_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_seen_ip: str | None = None
    risk_score: int = 0


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordResetRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    new_password: str = Field(min_length=10, max_length=128)


class VerificationRequest(BaseModel):
    channel: str = Field(pattern="^(email|phone)$")


class VerificationConfirmRequest(BaseModel):
    channel: str = Field(pattern="^(email|phone)$")
    code: str = Field(min_length=6, max_length=128)


class MfaEnrollRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class SessionResponse(BaseModel):
    id: str
    client_id: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool = False
    auth_method: str = "password"
    risk_score: int = 0
    risk_reasons: list[str] = []
    step_up_at: datetime | None = None
    device_id: str | None = None


class AuditEventResponse(BaseModel):
    id: str
    event_type: str
    success: bool
    client_id: str | None
    ip_address: str | None
    details: dict[str, object] | None
    created_at: datetime


class AdminUserResponse(BaseModel):
    id: str
    email: str | None
    phone: str | None
    display_name: str
    is_active: bool
    is_platform_admin: bool
    mfa_enabled: bool
    email_verified: bool
    phone_verified: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class AdminUserUpdateRequest(BaseModel):
    is_active: bool | None = None
    unlock: bool = False


class AdminApplicationResponse(BaseModel):
    client_id: str
    name: str
    is_active: bool
    created_at: datetime


class AdminApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


class PasskeyRegistrationVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=64)
    credential: dict[str, Any]
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)
    label: str | None = Field(default=None, max_length=160)


class PasskeyAuthenticationVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=64)
    credential: dict[str, Any]
    client_id: str = Field(min_length=1, max_length=120)


class PasskeyRemoveRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)


class PasskeyResponse(BaseModel):
    id: str
    label: str | None
    device_type: str | None
    backed_up: bool
    created_at: datetime
    last_used_at: datetime | None
