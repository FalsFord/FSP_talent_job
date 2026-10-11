"""EndPoint UI extensions; identity and invitations belong to FSP Talent."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class EndpointState(Base):
    __tablename__ = 'endpoint_ui_state'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

class ChatMessage(Base):
    __tablename__ = 'endpoint_chat_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('invitations.id', ondelete='CASCADE'), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    text: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    __table_args__ = (UniqueConstraint('offer_id','sender_id','client_message_id',name='uq_endpoint_chat_retry'),)
