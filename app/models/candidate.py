import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class SkillSource(str, enum.Enum):
    self_declared = "self_declared"
    test_verified = "test_verified"
    case_verified = "case_verified"
    employer_verified = "employer_verified"


class SkillStatus(str, enum.Enum):
    claimed = "claimed"
    verified = "verified"
    stale = "stale"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    specialization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specializations.id"), nullable=False)
    grade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grades.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)

    specialization: Mapped["Specialization"] = relationship(back_populates="categories")
    grade: Mapped["Grade"] = relationship()
    candidates: Mapped[list["CandidateProfile"]] = relationship(back_populates="category")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    headline: Mapped[str | None] = mapped_column(String(256))
    city: Mapped[str | None] = mapped_column(String(128))
    remote_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String(64))
    about: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    declared_grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    confirmed_grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specializations.id"))
    grade_last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile_strength: Mapped[float] = mapped_column(Float, default=0.0)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy: Mapped[dict] = mapped_column(JSONB, default=dict)
    # --- подтверждение грейда и профиль (добавлено) ---
    grade_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grade_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_discoverable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_test_ratio: Mapped[float | None] = mapped_column(Float)       # доля баллов последнего зачётного теста (0..1)
    task_ratio: Mapped[float | None] = mapped_column(Float)            # сглаженная оценка регулярных заданий (0..1)
    last_micro_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    languages: Mapped[list] = mapped_column(JSONB, default=list)       # языки для тестирования (python/java/sql)
    search_text: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="candidate_profile")
    category: Mapped[Category | None] = relationship(back_populates="candidates")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    fsp_link: Mapped["FSPParticipantLink | None"] = relationship(back_populates="candidate", uselist=False)


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False)
    source: Mapped[SkillSource] = mapped_column(Enum(SkillSource), default=SkillSource.self_declared)
    status: Mapped[SkillStatus] = mapped_column(Enum(SkillStatus), default=SkillStatus.claimed)
    level: Mapped[int] = mapped_column(default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    candidate: Mapped[CandidateProfile] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship()


from app.models.fsp import FSPParticipantLink  # noqa: E402
from app.models.reference import Grade, Skill, Specialization  # noqa: E402
from app.models.user import User  # noqa: E402
