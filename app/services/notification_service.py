import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import Notification


async def notify(db: AsyncSession, user_id: uuid.UUID, type_: str, title: str, body: str = "",
                 payload: dict | None = None) -> None:
    """Добавляет in-app уведомление (commit — на стороне вызывающего)."""
    db.add(Notification(user_id=user_id, type=type_, title=title, body=body, payload=payload or {}))
