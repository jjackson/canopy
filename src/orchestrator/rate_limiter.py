"""Rate limiter: caps API calls per hour to prevent runaway spend."""
import time


class RateLimiter:
    """Track API calls and enforce a per-hour limit.

    Inspired by Super-Ralph's rate limiting pattern.
    """

    def __init__(self, max_calls_per_hour: int = 30):
        self.max_calls_per_hour = max_calls_per_hour
        self._timestamps: list[float] = []

    def _cleanup(self) -> None:
        """Remove timestamps older than 1 hour."""
        cutoff = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    @property
    def calls_this_hour(self) -> int:
        self._cleanup()
        return len(self._timestamps)

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls_per_hour - self.calls_this_hour)

    def can_proceed(self) -> bool:
        return self.calls_this_hour < self.max_calls_per_hour

    def record_call(self) -> None:
        self._timestamps.append(time.time())

    def summary(self) -> str:
        return f"{self.calls_this_hour}/{self.max_calls_per_hour} calls this hour ({self.remaining} remaining)"
