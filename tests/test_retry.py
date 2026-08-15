from src.orchestration.retry import decide_retry
from src.providers.base import ProviderError


def test_retryable_provider_error_uses_backoff() -> None:
    decision = decide_retry(ProviderError("busy", retryable=True), attempt=1, max_retries=3)
    assert decision.retry
    assert decision.delay_seconds == 2


def test_retry_limit_stops_retrying() -> None:
    decision = decide_retry(TimeoutError(), attempt=3, max_retries=3)
    assert not decision.retry
