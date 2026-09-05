import uuid
import httpx

from database.config.config import settings
from mpesa.service.mpesaAuth import MpesaAuth
from mpesa.service.mpesa import MpesaService


class MpesaReversalService:

    @staticmethod
    def generate_conversation_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    async def reverse_transaction(
            transaction_id: str,
            amount: float | None = None
    ):
        session_id = await MpesaAuth.get_session()
        encrypted_session_id = MpesaService.encrypt_value(session_id)

        url = (
            f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/reversal/"
        )

        payload = {
            "input_Country": settings.MPESA_COUNTRY,
            "input_ServiceProviderCode": settings.MPESA_SHORTCODE,
            "input_ThirdPartyConversationID": MpesaReversalService.generate_conversation_id(),
            "input_TransactionID": transaction_id
        }

        # optional: omit this for full reversal
        if amount is not None:
            payload["input_ReversalAmount"] = str(amount)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {encrypted_session_id}",
            "Origin": "*"
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                url,
                json=payload,
                headers=headers
            )

        return response.json()
