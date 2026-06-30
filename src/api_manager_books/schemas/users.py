import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from api_manager_books.schemas.enums import UserRole
from api_manager_books.security.password_policy import validate_password_strength


class UserBase(BaseModel):
    """Базовые поля пользователя."""

    email: EmailStr
    role: UserRole = UserRole.USER


class UserCreate(UserBase):
    """Данные для создания пользователя."""

    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: str) -> str:
        """Проверяет минимальную надежность пароля."""
        return validate_password_strength(password)


class UserUpdate(BaseModel):
    """Данные для обновления пользователя."""

    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: str | None) -> str | None:
        """Проверяет пароль, если он передан."""
        if password is None:
            return None
        return validate_password_strength(password)


class UserRead(UserBase):
    """Публичное представление пользователя."""

    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


