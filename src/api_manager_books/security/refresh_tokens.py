import hashlib
import secrets

REFRESH_TOKEN_BYTES = 48


def create_refresh_token() -> str:
    """Создать непрозрачный refresh token."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> bytes:
    """Получить необратимый хеш refresh token для хранения."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def verify_refresh_token(token: str, token_hash: bytes) -> bool:
    """Сверить refresh token с сохраненным хешем."""
    return secrets.compare_digest(hash_refresh_token(token), token_hash)
