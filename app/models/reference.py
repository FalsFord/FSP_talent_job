import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Specialization(Base):
    __tablename__ = "specializations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[list["Category"]] = relationship(back_populates="specialization")


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


from app.models.candidate import Category  # noqa: E402
