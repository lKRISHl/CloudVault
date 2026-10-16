"""Operator/test probe of the real isolated renderer. Source bytes arrive only on stdin."""

import asyncio
import json
import sys

from app.services.previews import MAX_SOURCE, isolated_render


async def main():
    data = sys.stdin.buffer.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError("Preview fixture exceeds source limit")
    result = await isolated_render(data, int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print(json.dumps(result.model_dump()))


if __name__ == "__main__":
    asyncio.run(main())
