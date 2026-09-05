import uuid
import httpx

from sqlalchemy.orm import Session

from database.config.config import settings
from mpesa.service.mpesaAuth import MpesaAuth
from mpesa.service.mpesa import MpesaService


class MpesaB2CService:

    @staticmethod
    def generate_transaction_reference() -> str:
        return f"PY{uuid.uuid4().hex[:10]}"  # max 20 chars

    @staticmethod
    def generate_conversation_id() -> str:
        return uuid.uuid4().hex  # max 40 chars

    @staticmethod
    async def initiate_employee_payment(
            db: Session,
            employee_id: str,
            phone: str,
            amount: float,
            payment_reason: str = "Salary payment"
    ):
        transaction_reference = MpesaB2CService.generate_transaction_reference()
        conversation_id = MpesaB2CService.generate_conversation_id()

        response = await MpesaB2CService.send_b2c_payment_request(
            phone=phone,
            amount=amount,
            transaction_reference=transaction_reference,
            conversation_id=conversation_id,
            payment_reason=payment_reason
        )

        return {
            "message": "Employee payment request sent",
            "employee_id": employee_id,
            "transaction_reference": transaction_reference,
            "conversation_id": conversation_id,
            "mpesa_response": response
        }

    @staticmethod
    async def send_b2c_payment_request(
            phone: str,
            amount: float,
            transaction_reference: str,
            conversation_id: str,
            payment_reason: str
    ):
        session_id = await MpesaAuth.get_session()

        encrypted_session_id = MpesaService.encrypt_value(session_id)

        url = (
            f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/b2cPayment/"
        )

        payload = {
            "input_Amount": str(amount),
            "input_Country": settings.MPESA_COUNTRY,
            "input_Currency": settings.MPESA_CURRENCY,
            "input_CustomerMSISDN": phone,
            "input_ServiceProviderCode": settings.MPESA_SHORTCODE,
            "input_ThirdPartyConversationID": conversation_id,
            "input_TransactionReference": transaction_reference,
            "input_PaymentItemsDesc": payment_reason
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
