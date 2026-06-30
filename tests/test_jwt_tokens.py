from datetime import UTC, datetime

import jwt
import pytest

from api_manager_books.api.security import jwt_tokens


def test_access_token_decodes_valid_payload():
    """Проверяет декодирование корректного access token."""
    token = jwt_tokens.create_access_token(
        {
            "sub": "user-id",
            "sid": "session-id",
            "role": "user",
            "type": "access",
        }
    )

    payload = jwt_tokens.decode_access_token(token)

    assert payload["sub"] == "user-id"
    assert payload["sid"] == "session-id"
    assert payload["type"] == "access"


def test_decode_access_token_rejects_oversized_token():
    """Проверяет отказ до JWT parser для слишком большого токена."""
    token = "x" * (jwt_tokens.MAX_JWT_TOKEN_BYTES + 1)

    with pytest.raises(jwt.InvalidTokenError):
        jwt_tokens.decode_access_token(token)


def test_access_token_default_lifetime_is_15_minutes():
    """Проверяет срок жизни access token по умолчанию."""
    token = jwt_tokens.create_access_token(
        {
            "sub": "user-id",
            "sid": "session-id",
            "role": "user",
            "type": "access",
        }
    )

    payload = jwt.decode(
        token,
        jwt_tokens.PUBLIC_KEY_PEM,
        algorithms=[jwt_tokens.ALGORITHM],
        options={"verify_exp": False},
    )
    expires_at = datetime.fromtimestamp(payload["exp"], UTC)

    lifetime = expires_at - datetime.now(UTC)
    assert 14 * 60 <= lifetime.total_seconds() <= 15 * 60
