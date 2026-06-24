from enum import Enum


class UserRole(str, Enum):
    """Роли пользователей."""

    ADMIN = "admin"
    USER = "user"
