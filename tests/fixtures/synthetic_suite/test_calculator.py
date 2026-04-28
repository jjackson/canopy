"""Synthetic test fixture for test-audit. Each test is documented with the
expected verdict so the integration test can assert against it.
"""
from unittest.mock import patch


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


# expected: keep — clear assertion of behavior
def test_add_returns_sum():
    assert add(2, 3) == 5


# expected: keep — sibling of test_add_returns_sum but different input
def test_add_with_negatives():
    assert add(-1, -2) == -3


# expected: prune — tautology, no real assertion
def test_always_passes():
    assert True


# expected: prune — no assertion at all
def test_no_assertion():
    x = add(1, 2)


# expected: prune (env-fragile) — relies on an absent dependency
def test_env_fragile():
    import nonexistent_module  # noqa: F401
    assert nonexistent_module.value == 1


# expected: refactor — name says one thing, body asserts another
def test_subtraction_works():
    assert add(2, 3) == 5


# expected: prune — mock of CUT (`add` IS the code under test)
def test_add_with_mock_of_cut():
    with patch(__name__ + ".add", return_value=99):
        assert add(1, 2) == 99
