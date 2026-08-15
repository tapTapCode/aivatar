from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.limit = requests_per_minute
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        queue = self._requests[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
        queue.append(now)


def authorize_request(
    request: Request, *, api_key: str | None, limiter: SlidingWindowRateLimiter
) -> str:
    supplied = request.headers.get("x-api-key")
    if api_key and supplied != api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
    owner_id = request.headers.get("x-owner-id", "local-development")
    if not owner_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "x-owner-id must not be empty")
    limiter.check(owner_id)
    return owner_id
