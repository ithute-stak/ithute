from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=8)


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
