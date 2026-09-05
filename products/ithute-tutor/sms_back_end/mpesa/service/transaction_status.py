import uuid
import httpx

from database.config.config import settings
from mpesa.service.mpesaAuth import MpesaAuth
from mpesa.service.mpesa import MpesaService


class MpesaTransactionStatusService:

    @staticmethod
    def generate_conversation_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    async def query_transaction_status(query_reference: str) -> dict:
        session_id = await MpesaAuth.get_session()
        encrypted_session_id = MpesaService.encrypt_value(session_id)

        url = (
            f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/queryTransactionStatus/"
        )

        params = {
            "input_QueryReference": query_reference,
            "input_ServiceProviderCode": settings.MPESA_SHORTCODE,
            "input_ThirdPartyConversationID": (
                MpesaTransactionStatusService.generate_conversation_id()
            ),
            "input_Country": settings.MPESA_COUNTRY,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {encrypted_session_id}",
            "Origin": "*"
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                url,
                params=params,
                headers=headers
            )

        return response.json()

    @staticmethod
    def is_completed(result: dict) -> bool:
        response_code = result.get("output_ResponseCode")

        if response_code != "INS-0":
            return False

        transaction_status = (
                result.get("output_ResponseTransactionStatus")
                or result.get("output_TransactionStatus")
        )

        reversed_status = result.get("output_Reversed")

        return (
                str(transaction_status).lower() == "completed"
                and str(reversed_status).lower() == "false"
        )
