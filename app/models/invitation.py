import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InvitationStatus(str, enum.Enum):
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    declined = "declined"
    withdrawn = "withdrawn"
    expired = "expired"


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employer_profiles.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False)
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vacancies.id"))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    salary_min: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(Enum(InvitationStatus), default=InvitationStatus.sent)
    contact_method: Mapped[str | None] = mapped_column(String(256))   # «способ связи» (ТЗ п.2.2)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employer: Mapped["EmployerProfile"] = relationship()
    candidate: Mapped["CandidateProfile"] = relationship()


from app.models.candidate import CandidateProfile  # noqa: E402
from app.models.employer import EmployerProfile  # noqa: E402
