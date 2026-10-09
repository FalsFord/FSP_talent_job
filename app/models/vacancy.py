import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.employer import WorkFormat


class ApplicationStatus(str, enum.Enum):
    submitted = "submitted"
    viewed = "viewed"
    accepted = "accepted"
    rejected = "rejected"


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    work_format: Mapped[WorkFormat | None] = mapped_column(Enum(WorkFormat))
    salary_min: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=False)
    trust_score: Mapped[float] = mapped_column(default=75.0)
    trust_flags: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False)
    cover_letter: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.submitted)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
