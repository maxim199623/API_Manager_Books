from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from api_manager_books.api.security.cert.jwt_keys import ensure_jwt_keys

ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

PRIVATE_KEY_PEM, PUBLIC_KEY_PEM = ensure_jwt_keys()


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Создать JWT access token, подписанный приватным RSA-ключом.
    """
    to_encode = data.copy()

    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(UTC) + expires_delta
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY_PEM, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """
    Проверить и декодировать JWT с использованием публичного ключа.
    """
    payload = jwt.decode(token, PUBLIC_KEY_PEM, algorithms=[ALGORITHM])
    return payload
