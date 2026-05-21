from datetime import datetime

import uuid

from sqlalchemy import String, DateTime, func, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from src.DB.base import Base
from  src.DB.Repository.UserRepository.Enums import UserRole

from sqlalchemy.types import Uuid

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False)

    role: Mapped[UserRole] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.USER,
    )

    session: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )