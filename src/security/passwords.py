import bcrypt


def hash_password(password: str) -> bytes:
    """Хеширует пароль для сохранения в БД."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    """Проверяет пароль пользователя по сохраненному хешу."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed)
