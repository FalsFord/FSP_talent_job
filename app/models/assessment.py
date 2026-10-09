import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SessionType(str, enum.Enum):
    onboarding = "onboarding"
    retest = "retest"


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    submitted = "submitted"
    expired = "expired"


class QuestionType(str, enum.Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    text = "text"


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    question_type: Mapped[QuestionType] = mapped_column(Enum(QuestionType), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict | None] = mapped_column(JSONB)
    correct_answer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False)
    session_type: Mapped[SessionType] = mapped_column(Enum(SessionType), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.in_progress)
    declared_grade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grades.id"), nullable=False)
    specialization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specializations.id"), nullable=False)
    question_ids: Mapped[list] = mapped_column(JSONB, default=list)
    score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column()
    outcome_grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # --- конвейер заданий (добавлено) ---
    purpose: Mapped[str] = mapped_column(String(16), default="onboarding")   # onboarding|up|down|reattest|micro
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_limit_s: Mapped[int | None] = mapped_column(Integer)
    scaled_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    result: Mapped[str | None] = mapped_column(String(16))                   # pass|borderline|fail
    integrity: Mapped[list] = mapped_column(JSONB, default=list)             # флаги анти-чита
    languages: Mapped[list] = mapped_column(JSONB, default=list)
    decision: Mapped[dict | None] = mapped_column(JSONB)

    candidate: Mapped["CandidateProfile"] = relationship()
    answers: Mapped[list["AssessmentAnswer"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_sessions.id"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_questions.id"), nullable=False)
    answer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column()

    session: Mapped[AssessmentSession] = relationship(back_populates="answers")


from app.models.candidate import CandidateProfile  # noqa: E402
