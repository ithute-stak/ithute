import asyncio
import os
from datetime import datetime, timezone

import psycopg
from redis import Redis


def _decision(username: str) -> str:
    if not username:
        return "DUNNO"
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "lelefamail"),
        user=os.getenv("POSTGRES_USER", "lelefamail"),
        password=os.getenv("POSTGRES_PASSWORD", "lelefamail_dev_password"),
        connect_timeout=3,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text, active, daily_limit FROM smtp_credentials WHERE lower(username)=lower(%s) LIMIT 1",
                (username,),
            )
            row = cur.fetchone()
    if row is None:
        return "DUNNO"
    credential_id, active, daily_limit = row
    if not active:
        return "REJECT SMTP credential is disabled"
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"smtp-daily:{credential_id}:{day}"
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), socket_connect_timeout=2, socket_timeout=2)
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 172800)
    if int(count) > int(daily_limit):
        return "DEFER_IF_PERMIT Daily SMTP credential limit reached"
    return "DUNNO"


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    values: dict[str, str] = {}
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text == "":
                try:
                    action = await asyncio.to_thread(_decision, values.get("sasl_username", ""))
                except Exception:
                    action = "DEFER_IF_PERMIT SMTP policy service temporary failure"
                writer.write(f"action={action}\n\n".encode("utf-8"))
                await writer.drain()
                values = {}
                continue
            if "=" in text:
                key, value = text.split("=", 1)
                values[key] = value
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 10031)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
