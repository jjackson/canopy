import time
import pytest
from orchestrator.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_allows_first_call(self):
        rl = RateLimiter(max_calls_per_hour=10)
        assert rl.can_proceed() is True

    def test_tracks_calls(self):
        rl = RateLimiter(max_calls_per_hour=10)
        rl.record_call()
        assert rl.calls_this_hour == 1

    def test_blocks_after_limit(self):
        rl = RateLimiter(max_calls_per_hour=3)
        rl.record_call()
        rl.record_call()
        rl.record_call()
        assert rl.can_proceed() is False

    def test_remaining(self):
        rl = RateLimiter(max_calls_per_hour=5)
        rl.record_call()
        rl.record_call()
        assert rl.remaining == 3

    def test_old_calls_expire(self):
        rl = RateLimiter(max_calls_per_hour=2)
        # Manually inject an old timestamp
        rl._timestamps.append(time.time() - 3700)  # > 1 hour ago
        rl._cleanup()
        assert rl.calls_this_hour == 0

    def test_summary(self):
        rl = RateLimiter(max_calls_per_hour=10)
        rl.record_call()
        summary = rl.summary()
        assert "1" in summary
        assert "10" in summary
