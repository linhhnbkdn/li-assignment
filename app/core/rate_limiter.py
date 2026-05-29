import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s.")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 30, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[user_id]
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                retry_after = int(self._window - (now - bucket[0])) + 1
                logger.warning(f"Rate limit exceeded: user_id={user_id}")
                raise RateLimitExceeded(retry_after=retry_after)
            bucket.append(now)
