import asyncio
import signal

from .config import get_settings
from .db import SessionLocal
from .events import process_due_events


_stop = asyncio.Event()


def _request_stop(*_) -> None:
    _stop.set()


async def run() -> None:
    settings = get_settings()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                await process_due_events(db, limit=100)
        except Exception:
            await asyncio.sleep(max(1.0, settings.event_worker_poll_seconds))
        try:
            await asyncio.wait_for(_stop.wait(), timeout=settings.event_worker_poll_seconds)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    asyncio.run(run())
