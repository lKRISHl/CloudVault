"""Credential-free Unix-socket renderer; never mount application data or allow networking."""

import asyncio
import contextlib
import json
import os
import signal
import struct
import sys
from pathlib import Path

MAX_SOURCE = 10 * 1024 * 1024
MAX_OUTPUT = 1500 * 1024
WORKER = Path(__file__).with_name("worker.py")


async def main():
    socket = Path("/preview/renderer.sock")
    socket.unlink(missing_ok=True)
    gate = asyncio.Semaphore(1)

    async def handle(reader, writer):
        process = None
        try:
            async with asyncio.timeout(12):
                size, page = struct.unpack("!II", await reader.readexactly(8))
                if size > MAX_SOURCE or page > 99:
                    raise ValueError("request_limit")
                # Bound queued memory as well as native concurrency.
                if gate.locked():
                    raise ValueError("renderer_busy")
                async with gate:
                    data = await reader.readexactly(size)
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-I",
                        str(WORKER),
                        str(page),
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                        env={
                            "PATH": "/usr/local/bin:/usr/bin:/bin",
                            "HOME": "/tmp",
                            "TMPDIR": "/tmp",
                        },
                    )

                    async def feed():
                        process.stdin.write(data)
                        await process.stdin.drain()
                        process.stdin.close()

                    feed_task = asyncio.create_task(feed())
                    try:
                        output = await process.stdout.read(MAX_OUTPUT + 1)
                        # read(n) may return a partial pipe frame; collect only up to the hard cap.
                        while len(output) <= MAX_OUTPUT:
                            chunk = await process.stdout.read(MAX_OUTPUT + 1 - len(output))
                            if not chunk:
                                break
                            output += chunk
                        if len(output) > MAX_OUTPUT:
                            raise ValueError("output_limit")
                        await feed_task
                        await process.wait()
                        if process.returncode != 0:
                            raise ValueError("worker_failed")
                    finally:
                        feed_task.cancel()
                        with contextlib.suppress(
                            asyncio.CancelledError, BrokenPipeError, ConnectionResetError
                        ):
                            await feed_task
                writer.write(struct.pack("!I", len(output)) + output)
                await writer.drain()
        except Exception:
            output = json.dumps(
                {"kind": "unsupported", "reason": "Renderer busy or resource limit reached"}
            ).encode()
            with contextlib.suppress(Exception):
                writer.write(struct.pack("!I", len(output)) + output)
                await writer.drain()
        finally:
            if process:
                # Kill native decoder descendants as well as the Python worker.
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                if process.returncode is None:
                    await process.wait()
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=str(socket), limit=64 * 1024)
    os.chmod(socket, 0o600)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
