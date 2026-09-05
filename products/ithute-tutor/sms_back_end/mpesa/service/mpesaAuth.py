# mpesa/service/mpesaAuth.py

import time
from mpesa.service.mpesa import MpesaService


class MpesaAuth:
    session_id = None
    session_created_at = 0
    SESSION_DURATION = 3600

    @classmethod
    async def get_session(cls, force_refresh: bool = False):
        now = time.time()

        if (
            not force_refresh
            and cls.session_id
            and now - cls.session_created_at < cls.SESSION_DURATION
        ):
            return cls.session_id

        response = await MpesaService.generate_session()

        session_id = response.get("output_SessionID")

        if not session_id:
            raise Exception(f"Failed to generate M-Pesa session: {response}")

        cls.session_id = session_id
        cls.session_created_at = now

        return cls.session_id