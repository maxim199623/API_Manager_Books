import pytest
from pydantic import ValidationError

from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate, UserUpdate
from api_manager_books.security.password_policy import (
    WeakPasswordError,
    validate_password_strength,
)


def test_password_shorter_than_12_chars_is_rejected():
    """Проверяет отказ для короткого пароля."""
    with pytest.raises(WeakPasswordError):
        validate_password_strength("short")


def test_default_password_is_rejected():
    """Проверяет отказ для известного слабого пароля."""
    with pytest.raises(WeakPasswordError):
        validate_password_strength("default")


@pytest.mark.parametrize(
    "password",
    [
        "aaaaaaaaaaaa",
        "123456789012",
        "password12345",
        "qwerty123456",
    ],
)
def test_weak_password_patterns_are_rejected(password: str):
    """Проверяет отказ для слабых шаблонов пароля."""
    with pytest.raises(WeakPasswordError):
        validate_password_strength(password)


def test_valid_password_is_accepted():
    """Проверяет прием валидного пароля."""
    assert validate_password_strength("valid-password") == "valid-password"


def test_password_with_two_character_classes_is_accepted():
    """Проверяет прием пароля с двумя классами символов."""
    assert validate_password_strength("valid-password-42") == "valid-password-42"


def test_user_create_rejects_weak_password():
    """Проверяет валидацию пароля при создании пользователя."""
    with pytest.raises(ValidationError):
        UserCreate(
            email="user@example.com",
            password="short",
            role=UserRole.USER,
        )


def test_user_update_accepts_password_none():
    """Проверяет, что отсутствие пароля при обновлении допустимо."""
    payload = UserUpdate(password=None)

    assert payload.password is None


def test_user_update_rejects_weak_password():
    """Проверяет валидацию переданного пароля при обновлении."""
    with pytest.raises(ValidationError):
        UserUpdate(password="short")
