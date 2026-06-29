import bcrypt
import anyio

BCRYPT_ROUNDS = 13


def hash_password(password: str) -> bytes:
    """Хеширует пароль для сохранения в БД."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def verify_password(password: str, hashed: bytes) -> bool:
    """Проверяет пароль пользователя по сохраненному хешу."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


async def verify_password_async(password: str, hashed: bytes) -> bool:
    """Выносит bcrypt-проверку из event loop."""
    return await anyio.to_thread.run_sync(verify_password, password, hashed)
