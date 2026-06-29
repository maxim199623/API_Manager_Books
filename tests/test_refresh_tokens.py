from api_manager_books.security.refresh_tokens import (
    create_refresh_token,
    hash_refresh_token,
    verify_refresh_token,
)


def test_refresh_token_is_random_and_long_enough():
    """Проверяет базовые свойства refresh token."""
    token = create_refresh_token()

    assert token
    assert len(token) >= 64


def test_refresh_token_hash_is_not_plain_token_and_verifies():
    """Проверяет хеширование и безопасную сверку refresh token."""
    token = create_refresh_token()
    token_hash = hash_refresh_token(token)

    assert token_hash != token.encode()
    assert verify_refresh_token(token, token_hash)
    assert not verify_refresh_token("wrong-token", token_hash)
