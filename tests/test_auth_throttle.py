from datetime import timedelta

import pytest

from api_manager_books.security.auth_throttle import AuthThrottle, TooManyAuthAttemptsError


def test_target_limit_blocks_after_five_failures():
    throttle = AuthThrottle()
    key = "login:user@example.com"

    for _ in range(5):
        throttle.record_failure(key, limit=5, window=timedelta(minutes=15))

    with pytest.raises(TooManyAuthAttemptsError):
        throttle.check(key, limit=5, window=timedelta(minutes=15))


def test_success_clears_target_counter():
    throttle = AuthThrottle()
    key = "login:user@example.com"

    for _ in range(5):
        throttle.record_failure(key, limit=5, window=timedelta(minutes=15))

    throttle.clear(key)
    throttle.check(key, limit=5, window=timedelta(minutes=15))


def test_old_failures_are_pruned():
    now = 1_000.0
    throttle = AuthThrottle(clock=lambda: now)
    key = "login:user@example.com"

    for _ in range(5):
        throttle.record_failure(key, limit=5, window=timedelta(seconds=10))

    throttle._clock = lambda: now + 11
    throttle.check(key, limit=5, window=timedelta(seconds=10))
