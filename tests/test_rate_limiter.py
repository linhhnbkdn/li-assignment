import time

import pytest

from app.core.rate_limiter import RateLimitExceeded, SlidingWindowRateLimiter


def test_allows_requests_under_limit():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    limiter.check("user-1")  # 3rd — still ok


def test_raises_on_limit_exceeded():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    limiter.check("user-1")
    with pytest.raises(RateLimitExceeded):
        limiter.check("user-1")  # 4th — exceeded


def test_different_users_isolated():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-2")  # different user — should not raise


def test_window_resets_old_requests(monkeypatch):
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
    fake_time = [0.0]
    monkeypatch.setattr("app.core.rate_limiter.time.monotonic", lambda: fake_time[0])

    limiter.check("user-1")
    limiter.check("user-1")

    fake_time[0] = 11.0  # advance past window
    limiter.check("user-1")  # old requests expired — should not raise


def test_retry_after_is_positive():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("user-1")
    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check("user-1")
    assert exc_info.value.retry_after > 0
