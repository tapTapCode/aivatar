from __future__ import annotations

from dataclasses import dataclass

from src.providers.base import ProviderError


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float
    reason: str


def decide_retry(error: Exception, *, attempt: int, max_retries: int) -> RetryDecision:
    if attempt >= max_retries:
        return RetryDecision(False, 0, "retry limit reached")
    if isinstance(error, ProviderError) and error.retryable:
        return RetryDecision(True, min(30.0, 2.0**attempt), "retryable provider error")
    if isinstance(error, TimeoutError | ConnectionError):
        return RetryDecision(True, min(30.0, 2.0**attempt), "transient transport error")
    return RetryDecision(False, 0, "non-retryable error")
