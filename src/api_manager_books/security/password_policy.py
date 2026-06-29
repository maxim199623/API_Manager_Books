import string


class WeakPasswordError(ValueError):
    """Пароль не соответствует минимальной политике безопасности."""


COMMON_WEAK_PASSWORDS = {
    "password12345",
    "qwerty123456",
    "adminadmin123",
    "letmein123456",
    "welcome12345",
    "changeme12345",
}


def _character_class_count(password: str) -> int:
    classes = [
        any(char.isalpha() for char in password),
        any(char.isdigit() for char in password),
        any(char in string.punctuation for char in password),
    ]
    return sum(classes)


def validate_password_strength(password: str) -> str:
    """Проверить минимальную надежность пароля."""
    normalized = password.lower()
    if len(password) < 12:
        raise WeakPasswordError("Password is too weak")
    if len(set(password)) == 1:
        raise WeakPasswordError("Password is too weak")
    if _character_class_count(password) < 2:
        raise WeakPasswordError("Password is too weak")
    if normalized in COMMON_WEAK_PASSWORDS:
        raise WeakPasswordError("Password is too weak")
    return password
