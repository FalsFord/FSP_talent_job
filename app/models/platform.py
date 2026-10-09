"""Платформенные модели: уведомления, журнал приглашений, раскрытие контактов, токены почты, подборки, задания."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvitationEvent(Base):
    """Неизменяемый журнал статусов приглашения."""

    __tablename__ = "invitation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invitation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invitations.id", ondelete="CASCADE"), index=True, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)       # candidate | employer | system
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactReveal(Base):
    """ЕДИНСТВЕННЫЙ источник права работодателя видеть контакты кандидата (ТЗ п.2.2): принятое приглашение
    или собственный отклик кандидата. Любая выдача контактов проверяется по этой таблице."""

    __tablename__ = "contact_reveals"
    __table_args__ = (UniqueConstraint("candidate_id", "employer_id", name="uq_contact_reveal_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_profiles.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)      # invitation | application
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), default="verify")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShortlistSnapshot(Base):
    """Снимок подборки: позволяет уточнять фильтры, не теряя ранее полученную выдачу (ТЗ, подбор)."""

    __tablename__ = "shortlist_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    need_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_needs.id", ondelete="CASCADE"), index=True, nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    results: Mapped[list] = mapped_column(JSONB, default=list)
    algorithm_version: Mapped[str] = mapped_column(String(16), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmployerTask(Base):
    """Короткое задание от работодателя (ТЗ: «регулярные задания»): решить или предложить подход."""

    __tablename__ = "employer_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    language: Mapped[str | None] = mapped_column(String(16))
    rubric: Mapped[list] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(16), default="manual")   # manual | rag
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    __table_args__ = (UniqueConstraint("task_id", "candidate_id", name="uq_task_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="assigned")     # assigned | submitted | reviewed
    answer: Mapped[str | None] = mapped_column(Text)
    auto_score: Mapped[float | None] = mapped_column(Float)
    reviewer_score: Mapped[float | None] = mapped_column(Float)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
