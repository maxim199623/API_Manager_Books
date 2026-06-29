import pytest

from api_manager_books.security.passwords import hash_password, verify_password, verify_password_async


def test_hash_password_uses_bcrypt_rounds_13():
    hashed = hash_password("valid-password-42")

    assert hashed.startswith(b"$2b$13$")


def test_verify_password_accepts_valid_password_and_rejects_wrong_password():
    hashed = hash_password("valid-password-42")

    assert verify_password("valid-password-42", hashed)
    assert not verify_password("wrong-password-42", hashed)


@pytest.mark.asyncio
async def test_verify_password_async_accepts_valid_password_and_rejects_wrong_password():
    hashed = hash_password("valid-password-42")

    assert await verify_password_async("valid-password-42", hashed)
    assert not await verify_password_async("wrong-password-42", hashed)
