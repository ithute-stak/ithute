from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=32)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetComplete(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class SessionOut(BaseModel):
    id: str
    created_at: str
    expires_at: str
    user_agent: str | None = None
    ip_address: str | None = None
    revoked: bool
    trusted_device_id: str | None = None
    risk_score: int = 0
    risk_level: str = "low"
    new_device: bool = False
    last_seen_at: str | None = None



class RecoveryCodesResponse(BaseModel):
    codes: list[str]
    remaining: int


class RecoveryCodeStatus(BaseModel):
    remaining: int
    generated: bool


class TrustedDeviceOut(BaseModel):
    id: str
    label: str | None = None
    first_seen_at: str
    last_seen_at: str
    first_ip_address: str | None = None
    last_ip_address: str | None = None
    first_user_agent: str | None = None
    trusted: bool
    revoked: bool


class TrustedDeviceLabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class SecurityEventOut(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    created_at: str
    metadata: dict = Field(default_factory=dict)


class PasskeyRegistrationRequest(BaseModel):
    flow_id: str = Field(min_length=20, max_length=256)
    credential: dict
    name: str = Field(default="Passkey", min_length=1, max_length=120)
    current_password: str = Field(min_length=8, max_length=256)


class PasskeyAuthenticationRequest(BaseModel):
    flow_id: str = Field(min_length=20, max_length=256)
    credential: dict


class PasskeyOut(BaseModel):
    id: str
    name: str
    created_at: str
    last_used_at: str | None = None
    device_type: str | None = None
    backed_up: bool = False
    revoked: bool = False
