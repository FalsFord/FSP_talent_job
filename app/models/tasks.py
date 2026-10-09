"""Модели RAG-конвейера заданий: корпус знаний, банк заданий, экземпляры заданий в попытках."""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base


class KnowledgeDocument(Base):
    """Документ корпуса (тестовое задание из открытых источников или авторская заметка). Хранится для retrieval."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("source", "path", name="uq_knowledge_source_path"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    company: Mapped[str | None] = mapped_column(String(128))
    languages: Mapped[list] = mapped_column(JSONB, default=list)
    grade_hint: Mapped[str | None] = mapped_column(String(16))
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    license: Mapped[str] = mapped_column(String(128), default="unknown")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_doc", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    languages: Mapped[list] = mapped_column(JSONB, default=list)
    grade_hint: Mapped[str | None] = mapped_column(String(16))
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)


class TaskItem(Base):
    """Статический пункт банка (вопросы с выбором): авторские или черновики LLM после проверки и утверждения."""

    __tablename__ = "task_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ext_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32), default="quiz_single")
    language: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    grade: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(64), default="general")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list)
    correct: Mapped[dict | list | str] = mapped_column(JSONB, nullable=False)   # ключ ответа; наружу не отдаётся
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)   # draft | active | retired
    origin: Mapped[str] = mapped_column(String(16), default="authored")             # authored | llm_draft
    exposure_count: Mapped[int] = mapped_column(Integer, default=0)
    answered_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskInstance(Base):
    """Конкретное задание, выданное в конкретной попытке (условие + скрытый ключ/тесты + ответ кандидата)."""

    __tablename__ = "task_instances"
    __table_args__ = (Index("ix_task_instances_session", "session_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    generator_id: Mapped[str] = mapped_column(String(96), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    grade: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), default="")
    seed: Mapped[int] = mapped_column(BigInteger, default=0)
    fingerprint: Mapped[str] = mapped_column(String(32), default="")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    public: Mapped[dict] = mapped_column(JSONB, default=dict)
    private: Mapped[dict] = mapped_column(JSONB, default=dict)      # ключ/тесты — только сервер
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    time_limit_s: Mapped[int] = mapped_column(Integer, default=120)
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    answer: Mapped[dict | None] = mapped_column(JSONB)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSONB)
    graded: Mapped[bool] = mapped_column(Boolean, default=False)


class AssessmentEvent(Base):
    """Анти-чит сигналы (потеря фокуса и т.п.). Это флаги для оценки уверенности, а не наказание."""

    __tablename__ = "assessment_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeneratorStat(Base):
    """Статистика по генераторам/пунктам: основа калибровки сложности и контроля экспозиции."""

    __tablename__ = "generator_stats"

    generator_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    shown: Mapped[int] = mapped_column(Integer, default=0)
    scored: Mapped[int] = mapped_column(Integer, default=0)
    score_sum: Mapped[float] = mapped_column(Float, default=0.0)


from app.models.assessment import AssessmentSession  # noqa: E402,F401
