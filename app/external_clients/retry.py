import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import httpx


async def with_retry(
    request_func: Callable[[], Coroutine[Any, Any, httpx.Response]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> httpx.Response:
    """
    Executes an async httpx request with exponential backoff retry.

    - Retries on TimeoutException and 5xx responses.
    - On 429 responses, waits for the Retry-After header value (in seconds).
    - Re-raises TimeoutException after exhausting all retries.
    - Returns the last response after exhausting retries on 5xx.
    """
    last_response: httpx.Response | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await request_func()
        except httpx.TimeoutException:
            if attempt == max_retries:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
            continue

        if response.status_code == 429:
            retry_after = float(
                response.headers.get("Retry-After", base_delay * (2**attempt))
            )
            await asyncio.sleep(retry_after)
            last_response = response
            continue

        if response.status_code >= 500 and attempt < max_retries:
            await asyncio.sleep(base_delay * (2**attempt))
            last_response = response
            continue

        return response

    return last_response  # type: ignore[return-value]
