import traceback
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Student
from database.multi_tenant_school_management.schemas.notification import NotificationRead
from mpesa.service.crud_mpesa import (
    get_mpesa_transaction_by_conversation_id,
    update_mpesa_transaction_status,
)

from mpesa.service.mpesa_reversal import MpesaReversalService

from routes.finance_management.service.create_fee_payment import (
    create_student_payment_nit,
)
from routes.service.notifications import create_notification
from ws.broadcasting.stundent_payment import student_payment_socket


class MpesaCallbackService:

    @staticmethod
    async def handle_student_fee_c2b_callback(db: Session, payload: dict):

        data = payload.get("data") or {}
        transaction = data.get("transaction") or {}
        mpesa_response = data.get("mpesa_response") or {}

        response_code = (
                mpesa_response.get("input_ResultCode")
                or mpesa_response.get("output_ResponseCode")
                or payload.get("input_ResultCode")
                or payload.get("output_ResponseCode")
        )

        conversation_id = (
                transaction.get("conversation_id")
                or payload.get("conversation_id")
                or mpesa_response.get("input_ThirdPartyConversationID")
                or mpesa_response.get("output_ThirdPartyConversationID")
                or payload.get("input_ThirdPartyConversationID")
                or payload.get("output_ThirdPartyConversationID")
        )

        if not isinstance(conversation_id, str):
            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Invalid conversation ID",
                "output_ThirdPartyConversationID": ""
            }

        tx = get_mpesa_transaction_by_conversation_id(
            db=db,
            conversation_id=conversation_id
        )

        if not tx:
            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Transaction not found in school DB",
                "output_ThirdPartyConversationID": conversation_id
            }

        if tx.status == "COMPLETED":
            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Already recorded",
                "output_ThirdPartyConversationID": conversation_id
            }

        if tx.status == "REVERSED":
            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Transaction already reversed",
                "output_ThirdPartyConversationID": conversation_id
            }

        mpesa_transaction_id = (
                mpesa_response.get("input_TransactionID")
                or mpesa_response.get("output_TransactionID")
                or payload.get("input_TransactionID")
                or payload.get("output_TransactionID")
        )

        if not isinstance(mpesa_transaction_id, str):
            mpesa_transaction_id = ""

        if response_code != "INS-0":
            update_mpesa_transaction_status(
                db=db,
                tx=tx,
                status="FAILED",
                mpesa_transaction_id=mpesa_transaction_id or None
            )

            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Payment failed",
                "output_ThirdPartyConversationID": conversation_id
            }

        if not mpesa_transaction_id:
            update_mpesa_transaction_status(
                db=db,
                tx=tx,
                status="FAILED"
            )

            return {
                "output_ResponseCode": "0",
                "output_ResponseDesc": "Missing M-Pesa transaction ID",
                "output_ThirdPartyConversationID": conversation_id
            }

        try:
            payment_payload = SimpleNamespace(
                amount_paid=float(tx.amount),
                student_id=tx.student_id,
                payment_method="mpesa",
                reference=mpesa_transaction_id
            )

            db_data = await create_student_payment_nit(db, payment_payload)

            update_mpesa_transaction_status(
                db=db,
                tx=tx,
                status="COMPLETED",
                mpesa_transaction_id=mpesa_transaction_id
            )



        except Exception as e:

            error_message = str(e)

            print("\n" + "=" * 80)

            print("❌ STUDENT PAYMENT DB FAILED")

            print(f"Student ID            : {tx.student_id}")

            print(f"Amount                : {tx.amount}")

            print(f"M-Pesa Transaction ID : {mpesa_transaction_id}")

            print(f"Conversation ID       : {conversation_id}")

            print(f"Error                 : {error_message}")

            print("\n📌 FULL TRACEBACK")

            traceback.print_exc()

            print("=" * 80 + "\n")

            update_mpesa_transaction_status(

                db=db,

                tx=tx,

                status="DB_FAILED",

                mpesa_transaction_id=mpesa_transaction_id,

            )

            try:

                reversal_response = (

                    await MpesaReversalService.reverse_transaction(

                        transaction_id=mpesa_transaction_id,

                        amount=float(tx.amount),

                    )

                )

                update_mpesa_transaction_status(

                    db=db,

                    tx=tx,

                    status="REVERSED",

                    mpesa_transaction_id=mpesa_transaction_id,

                )


            except Exception as reversal_error:

                reversal_response = {

                    "success": False,

                    "error": str(reversal_error),

                }

                print("\n" + "=" * 80)

                print("❌ REVERSAL FAILED")

                print(str(reversal_error))

                traceback.print_exc()

                print("=" * 80 + "\n")

            return {

                "success": False,

                "output_ResponseCode": "0",

                "output_ResponseDesc": "DB failed, reversal requested",

                "output_ThirdPartyConversationID": conversation_id,

                "debug": {

                    "db_error": error_message,

                    "student_id": str(tx.student_id),

                    "amount": float(tx.amount),

                    "mpesa_transaction_id": mpesa_transaction_id,

                    "conversation_id": conversation_id,

                    "reversal_response": reversal_response,

                },

            }

        response_data = {
            "success": True,
            "message": "Payment recorded successfully",
            "transaction": {
                "status": "COMPLETED",
                "conversation_id": conversation_id,
                "mpesa_transaction_id": mpesa_transaction_id,
                "student_id": str(tx.student_id),
                "amount_paid": float(tx.amount),
                "payment_method": "mpesa"
            },
            "payment": db_data.get("payment") if isinstance(db_data, dict) else None,
            "allocation_summary": (
                db_data.get("allocation_summary")
                if isinstance(db_data, dict)
                else None
            ),
            "allocations": (
                db_data.get("allocations")
                if isinstance(db_data, dict)
                else []
            ),
            "student_snapshot": (
                db_data.get("student_snapshot")
                if isinstance(db_data, dict)
                else None
            ),
            "receipt": (
                db_data.get("receipt")
                if isinstance(db_data, dict)
                else None
            )
        }

        student = (
            db.query(Student)
            .filter(Student.id == tx.student_id)
            .first()
        )

        if not student:
            update_mpesa_transaction_status(
                db=db,
                tx=tx,
                status="DB_FAILED",
                mpesa_transaction_id=mpesa_transaction_id,
            )

            raise HTTPException(
                status_code=404,
                detail="Attendance record not found"
            )

        notification = create_notification(
            db=db,
            channel='finance',
            title="Payment Received",
            message=f"M{float(tx.amount):.2f} payment received. Paying for Student: {student.admission_number} and Mpesa transaction ID is {mpesa_transaction_id}",
            event="PAYMENT_COMPLETED",
        )

        notification_data = NotificationRead.model_validate(
            notification
        ).model_dump()

        await student_payment_socket(
            data=response_data,
            notification=notification_data,
        )

        return response_data