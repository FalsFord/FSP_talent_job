import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class WorkFormat(str, enum.Enum):
    remote = "remote"
    office = "office"
    hybrid = "hybrid"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(256))
    industry: Mapped[str | None] = mapped_column(String(128))
    trust_score: Mapped[float] = mapped_column(Float, default=70.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employers: Mapped[list["EmployerProfile"]] = relationship(back_populates="company")


class EmployerProfile(Base):
    __tablename__ = "employer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    position: Mapped[str | None] = mapped_column(String(128))
    contact_phone: Mapped[str | None] = mapped_column(String(64))

    user: Mapped["User"] = relationship(back_populates="employer_profile")
    company: Mapped[Company] = relationship(back_populates="employers")
    needs: Mapped[list["EmployerNeed"]] = relationship(back_populates="employer")


class EmployerNeed(Base):
    __tablename__ = "employer_needs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    work_format: Mapped[WorkFormat | None] = mapped_column(Enum(WorkFormat))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    search_text: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer: Mapped[EmployerProfile] = relationship(back_populates="needs")


from app.models.user import User  # noqa: E402
