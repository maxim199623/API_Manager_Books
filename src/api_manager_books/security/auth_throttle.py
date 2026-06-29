from collections import defaultdict, deque
from collections.abc import Callable
from datetime import timedelta


class TooManyAuthAttemptsError(Exception):
    """Слишком много неуспешных попыток авторизации."""


class AuthThrottle:
    """Ограничивает частые ошибки авторизации в памяти процесса."""

    def __init__(self, clock: Callable[[], float] | None = None):
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self._clock = clock

    def _now(self) -> float:
        if self._clock is None:
            import time

            return time.monotonic()
        return self._clock()

    def _prune(self, key: str, window: timedelta) -> deque[float]:
        now = self._now()
        attempts = self._attempts[key]
        threshold = now - window.total_seconds()
        while attempts and attempts[0] <= threshold:
            attempts.popleft()
        return attempts

    def check(self, key: str, *, limit: int, window: timedelta) -> None:
        attempts = self._prune(key, window)
        if len(attempts) >= limit:
            raise TooManyAuthAttemptsError

    def record_failure(self, key: str, *, limit: int, window: timedelta) -> None:
        attempts = self._prune(key, window)
        attempts.append(self._now())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)
