import base64
import httpx
import asyncio

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import HTTPException

from database.config.config import settings


class MpesaService:

    @staticmethod
    def encrypt_value(value: str) -> str:
        pem_public_key = f"""
        -----BEGIN PUBLIC KEY-----
        {settings.MPESA_PUBLIC_KEY}
        -----END PUBLIC KEY-----
        """

        public_key = serialization.load_pem_public_key(
            pem_public_key.encode()
        )

        encrypted = public_key.encrypt(
            value.encode(),
            padding.PKCS1v15()
        )

        return base64.b64encode(encrypted).decode()

    @staticmethod
    async def generate_session():
        encrypted_key = MpesaService.encrypt_value(
            settings.MPESA_API_KEY
        )

        url = (
            f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/getSession/"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {encrypted_key}",
            "Origin": "*"
        }

        try:
            timeout = httpx.Timeout(60.0, connect=60.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)

            response.raise_for_status()

            data = response.json()

            session_id = data.get("output_SessionID")

            if not session_id:
                raise HTTPException(
                    status_code=400,
                    detail=data
                )

            # M-Pesa docs say session can take up to 30s to become active
            await asyncio.sleep(30)

            return data

        except httpx.ConnectTimeout:
            raise HTTPException(
                status_code=504,
                detail="M-Pesa connection timeout."
            )

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=e.response.text
            )
