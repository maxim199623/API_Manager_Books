import conftest as repository_conftest
import pytest


@pytest.mark.asyncio
async def test_unavailable_repository_backend_is_not_pinged_repeatedly(monkeypatch):
    ping_calls = 0

    class UnavailableDBManager:
        def __init__(self, settings, base):
            pass

        async def ping(self):
            nonlocal ping_calls
            ping_calls += 1
            return False

        async def dispose(self):
            pass

    async def consume_unavailable_backend():
        with pytest.raises(pytest.skip.Exception):
            async for _ in repository_conftest._managed_repository_db(object(), "postgres"):
                pass

    monkeypatch.setattr(repository_conftest, "AsyncDBManager", UnavailableDBManager)
    monkeypatch.delenv("API_MANAGER_BOOKS_REPOSITORY_BACKENDS", raising=False)
    repository_conftest._UNAVAILABLE_REPOSITORY_BACKENDS.clear()

    try:
        await consume_unavailable_backend()
        await consume_unavailable_backend()
    finally:
        repository_conftest._UNAVAILABLE_REPOSITORY_BACKENDS.clear()

    assert ping_calls == 1


@pytest.mark.asyncio
async def test_explicit_repository_backend_fails_when_unavailable(monkeypatch):
    class UnavailableDBManager:
        def __init__(self, settings, base):
            pass

        async def ping(self):
            return False

        async def dispose(self):
            pass

    monkeypatch.setattr(repository_conftest, "AsyncDBManager", UnavailableDBManager)
    monkeypatch.setenv("API_MANAGER_BOOKS_REPOSITORY_BACKENDS", "postgres")
    repository_conftest._UNAVAILABLE_REPOSITORY_BACKENDS.clear()

    try:
        try:
            async for _ in repository_conftest._managed_repository_db(object(), "postgres"):
                pass
        except pytest.skip.Exception as exc:
            pytest.fail(f"explicit backend must fail, not skip: {exc}")
        except RuntimeError as exc:
            assert "postgres is not available" in str(exc)
        else:
            pytest.fail("explicit unavailable backend did not fail")
    finally:
        repository_conftest._UNAVAILABLE_REPOSITORY_BACKENDS.clear()
