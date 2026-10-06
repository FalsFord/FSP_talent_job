import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FSPParticipantLink(Base):
    __tablename__ = "fsp_participant_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id"), unique=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped["CandidateProfile"] = relationship(back_populates="fsp_link")
    achievements: Mapped[list["FSPAchievement"]] = relationship(back_populates="link", cascade="all, delete-orphan")


class FSPAchievement(Base):
    __tablename__ = "fsp_achievements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fsp_participant_links.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    event_name: Mapped[str] = mapped_column(String(256), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    rank: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    link: Mapped[FSPParticipantLink] = relationship(back_populates="achievements")


from app.models.candidate import CandidateProfile  # noqa: E402
