import json
from collections.abc import AsyncIterator
import httpx

async def iter_sse(response: httpx.Response) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        if line.startswith('data:'):
            data = line[5:].strip()
            if data: yield f'data: {data}\n\n'
