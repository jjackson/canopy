"""Circuit breaker: stops pipeline after consecutive failures."""


class CircuitBreaker:
    """Track consecutive failures and trip after threshold.

    Inspired by Citadel's pattern: after N consecutive failures,
    stop and try a different approach rather than retrying.
    """

    def __init__(self, max_failures: int = 3):
        self.max_failures = max_failures
        self.consecutive_failures = 0
        self.recent_failures: list[str] = []

    @property
    def is_open(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    @property
    def open_reason(self) -> str:
        return "; ".join(self.recent_failures[-self.max_failures:])

    def record_failure(self, reason: str) -> None:
        self.consecutive_failures += 1
        self.recent_failures.append(reason)

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.recent_failures.clear()
