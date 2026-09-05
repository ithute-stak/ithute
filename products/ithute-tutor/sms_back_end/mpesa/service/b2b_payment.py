import uuid
import httpx

from sqlalchemy.orm import Session

from database.config.config import settings
from mpesa.service.mpesaAuth import MpesaAuth
from mpesa.service.mpesa import MpesaService


class MpesaB2BService:

    @staticmethod
    def generate_transaction_reference() -> str:
        return f"B2B{uuid.uuid4().hex[:10]}"  # max 20 chars

    @staticmethod
    def generate_conversation_id() -> str:
        return uuid.uuid4().hex  # max 40 chars

    @staticmethod
    async def initiate_supplier_payment(
        db: Session,
        supplier_id: str,
        receiver_party_code: str,
        amount: float,
        description: str = "Supplier payment"
    ):
        transaction_reference = MpesaB2BService.generate_transaction_reference()
        conversation_id = MpesaB2BService.generate_conversation_id()

        response = await MpesaB2BService.send_b2b_payment_request(
            receiver_party_code=receiver_party_code,
            amount=amount,
            transaction_reference=transaction_reference,
            conversation_id=conversation_id,
            description=description
        )

        return {
            "message": "Supplier payment request sent",
            "supplier_id": supplier_id,
            "transaction_reference": transaction_reference,
            "conversation_id": conversation_id,
            "mpesa_response": response
        }

    @staticmethod
    async def send_b2b_payment_request(
        receiver_party_code: str,
        amount: float,
        transaction_reference: str,
        conversation_id: str,
        description: str
    ):
        session_id = await MpesaAuth.get_session()
        encrypted_session_id = MpesaService.encrypt_value(session_id)

        url = (
            f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/b2bPayment/"
        )

        payload = {
            "input_Amount": str(amount),
            "input_Country": settings.MPESA_COUNTRY,
            "input_Currency": settings.MPESA_CURRENCY,
            "input_PrimaryPartyCode": settings.MPESA_SHORTCODE,
            "input_ReceiverPartyCode": receiver_party_code,
            "input_ThirdPartyConversationID": conversation_id,
            "input_TransactionReference": transaction_reference,
            "input_PurchasedItemsDesc": description
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {encrypted_session_id}",
            "Origin": "*"
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers
            )

        return response.json()