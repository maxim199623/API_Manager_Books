import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from api_manager_books.schemas.enums import UserRole


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.USER


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = None


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInDB(UserBase):
    id: uuid.UUID
    password_hash: bytes
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
