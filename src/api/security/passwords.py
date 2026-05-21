import bcrypt


def hash_password(password: str) -> bytes:
    """
    Хеширует пароль в bcrypt и возвращает bytes.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    """
    Проверяет пароль против bcrypt-хеша из БД (bytes).
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed)