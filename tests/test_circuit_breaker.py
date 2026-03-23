import pytest
from orchestrator.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(max_failures=3)
        assert cb.is_open is False

    def test_stays_closed_after_one_failure(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("test error")
        assert cb.is_open is False

    def test_opens_after_max_failures(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("error 1")
        cb.record_failure("error 2")
        cb.record_failure("error 3")
        assert cb.is_open is True

    def test_success_resets_counter(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("error 1")
        cb.record_failure("error 2")
        cb.record_success()
        cb.record_failure("error 3")
        assert cb.is_open is False

    def test_tracks_failure_reasons(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("timeout")
        cb.record_failure("parse error")
        assert len(cb.recent_failures) == 2
        assert "timeout" in cb.recent_failures

    def test_reason_when_open(self):
        cb = CircuitBreaker(max_failures=2)
        cb.record_failure("error A")
        cb.record_failure("error B")
        assert "error A" in cb.open_reason
        assert "error B" in cb.open_reason

    def test_consecutive_count(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("a")
        cb.record_failure("b")
        assert cb.consecutive_failures == 2

    def test_reset(self):
        cb = CircuitBreaker(max_failures=2)
        cb.record_failure("a")
        cb.record_failure("b")
        cb.reset()
        assert cb.is_open is False
        assert cb.consecutive_failures == 0
