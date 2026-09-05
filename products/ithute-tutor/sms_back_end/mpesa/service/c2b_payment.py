import uuid
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.config.config import settings
from database.multi_tenant_school_management.models import Student
from mpesa.service.crud_mpesa import create_pending_mpesa_transaction, update_mpesa_transaction_status
from mpesa.service.mpesa import MpesaService
from mpesa.service.mpesaAuth import MpesaAuth


class MpesaC2BService:

    @staticmethod
    def generate_internal_reference(student_id: str) -> str:
        unique_id = uuid.uuid4().hex[:10]
        return f"STUDENT-FEE-{student_id}-{unique_id}"

    @staticmethod
    def generate_transaction_reference() -> str:
        return f"FEE{uuid.uuid4().hex[:8]}"  # max 20 chars

    @staticmethod
    def generate_conversation_id() -> str:
        return uuid.uuid4().hex  # 32 chars, max allowed is 40

    @staticmethod
    async def initiate_student_fee_payment(
        db: Session,
        student_id: UUID,
        phone: str,
        amount: float
    ):
        student = db.get(Student, student_id)

        if not student:
            raise HTTPException(404, "Student not found")

        internal_reference = MpesaC2BService.generate_internal_reference(
            str(student_id)
        )

        transaction_reference = MpesaC2BService.generate_transaction_reference()
        conversation_id = MpesaC2BService.generate_conversation_id()

        tx = create_pending_mpesa_transaction(
            db=db,
            student_id=str(student_id),
            conversation_id=conversation_id,
            transaction_reference=transaction_reference,
            amount=amount,
            phone=phone,
        )

        response = await MpesaC2BService.send_c2b_payment_request(
            phone=phone,
            amount=amount,
            transaction_reference=transaction_reference,
            conversation_id=conversation_id
        )

        if response.get("output_ResponseCode") == "INS-0":
            update_mpesa_transaction_status(db=db,tx=tx,status="REQUEST_SENT" )
        else:
            update_mpesa_transaction_status(db=db,tx=tx, status="FAILED")

        return {
            "transaction": {
                "student_id": student_id,
                "conversation_id": conversation_id,
                "transaction_reference": transaction_reference,
                "amount": amount,
                "status": tx.status
            },
            "mpesa_response": response
        }

    @staticmethod
    async def send_c2b_payment_request(
        phone: str,
        amount: float,
        transaction_reference: str,
        conversation_id: str,
    ):
        session_id = await MpesaAuth.get_session()
        encrypted_session_id = MpesaService.encrypt_value(session_id)

        url = (
             f"{settings.MPESA_BASE_URL}/{settings.MPESA_MODEL}/ipg/v2/"
            f"{settings.MPESA_MARKET}/c2bPayment/singleStage/"
        )

        payload = {
            "input_Amount": str(amount),
            "input_Country": settings.MPESA_COUNTRY,
            "input_Currency": settings.MPESA_CURRENCY,
            "input_CustomerMSISDN": phone,
            "input_ServiceProviderCode": settings.MPESA_SHORTCODE,
            "input_ThirdPartyConversationID": conversation_id,
            "input_TransactionReference": transaction_reference,
            "input_PurchasedItemsDesc": "School fees"
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

        print(response.json())

        return response.json()