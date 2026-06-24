import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from api_manager_books.schemas.enums import UserRole


class UserBase(BaseModel):
    """Базовые поля пользователя."""

    email: EmailStr
    role: UserRole = UserRole.USER


class UserCreate(UserBase):
    """Данные для создания пользователя."""

    password: str


class UserUpdate(BaseModel):
    """Данные для обновления пользователя."""

    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = None


class UserRead(UserBase):
    """Публичное представление пользователя."""

    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInDB(UserBase):
    """Представление пользователя в базе."""

    id: uuid.UUID
    password_hash: bytes
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
