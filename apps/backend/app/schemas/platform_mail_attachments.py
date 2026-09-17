from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlatformMailAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    content_base64: str = Field(min_length=1, max_length=7_500_000)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        filename = value.strip()
        if filename in {".", ".."} or any(char in filename for char in ("/", "\\", "\r", "\n")):
            raise ValueError("attachment filename is invalid")
        return filename


class PlatformMailAttachmentSendRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    text: str | None = Field(default=None, max_length=1_000_000)
    html: str | None = Field(default=None, max_length=2_000_000)
    attachments: list[PlatformMailAttachment] = Field(min_length=1, max_length=10)

    @field_validator("external_reference")
    @classmethod
    def normalize_external_reference(cls, value: str) -> str:
        return value.strip()

    @field_validator("recipient")
    @classmethod
    def normalize_recipient(cls, value: str) -> str:
        return value.strip().lower()
