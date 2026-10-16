"""Bounded ClamD INSTREAM client. Only an exact OK with fresh definitions releases bytes."""

import asyncio
import re
import struct
from contextlib import suppress
from datetime import UTC, datetime

from app.core.config import settings


class ScannerUnavailableError(Exception):
    """Sanitized failure; native responses may include private content/signature details."""


class ClamdScanner:
    async def connection(self):
        return await asyncio.wait_for(
            asyncio.open_connection(settings.CLAMD_HOST, settings.CLAMD_PORT, limit=2048), 5
        )

    async def reply(self, reader):
        return (await reader.readuntil(b"\0"))[:-1].decode("ascii", errors="strict")

    async def version(self):
        writer = None
        try:
            async with asyncio.timeout(5):
                reader, writer = await self.connection()
                writer.write(b"zVERSION\0")
                await writer.drain()
                value = await self.reply(reader)
                match = re.fullmatch(
                    r"ClamAV ([0-9][0-9A-Za-z.\-]{0,50})/([0-9]{1,12})/(.{1,64})", value
                )
                if not match:
                    raise ValueError("invalid scanner version")
                stamp = datetime.strptime(match[3], "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
                age = (datetime.now(UTC) - stamp).total_seconds()
                if not -300 <= age <= settings.SCAN_DEFINITION_MAX_AGE_SECONDS:
                    raise ValueError("scanner definitions stale")
                return f"{match[1]}/{match[2]}"
        except Exception:
            raise ScannerUnavailableError("Scanner unavailable or definitions stale") from None
        finally:
            if writer:
                writer.close()
                with suppress(Exception):
                    await asyncio.wait_for(writer.wait_closed(), 1)

    async def scan(self, chunks):
        writer = None
        try:
            async with asyncio.timeout(settings.SCAN_TIMEOUT_SECONDS):
                engine = await self.version()
                reader, writer = await self.connection()
                writer.write(b"zINSTREAM\0")
                await writer.drain()
                total = 0
                async for chunk in chunks:
                    if not isinstance(chunk, bytes) or not 0 < len(chunk) <= 65536:
                        raise ValueError("invalid scanner chunk")
                    total += len(chunk)
                    if total > settings.SCAN_MAX_BYTES:
                        raise ValueError("scanner input limit")
                    writer.write(struct.pack("!I", len(chunk)) + chunk)
                    await writer.drain()
                writer.write(b"\0\0\0\0")
                await writer.drain()
                result = await self.reply(reader)
                if result == "stream: OK":
                    return "clean", engine
                if result.startswith("stream: ") and result.endswith(" FOUND"):
                    return "blocked", engine
                raise ValueError("scanner did not return a complete verdict")
        except Exception:
            raise ScannerUnavailableError("Scan unavailable; content remains quarantined") from None
        finally:
            if writer:
                writer.close()
                with suppress(Exception):
                    await asyncio.wait_for(writer.wait_closed(), 1)
