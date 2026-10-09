from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import DomainError
from app.models.platform import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(unread_only: bool = False, limit: int = 50, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = (await db.execute(q.order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 100)))).scalars().all()
    unread = (await db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))).scalar_one()
    return {"unread": unread, "items": [{"id": n.id, "type": n.type, "title": n.title, "body": n.body, "payload": n.payload,
                                         "read": n.read_at is not None, "created_at": n.created_at} for n in rows]}


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(notification_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    n = await db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise DomainError("NOT_FOUND", "Notification not found", 404)
    if n.read_at is None:
        n.read_at = func.now()
    await db.commit()


@router.post("/read-all", status_code=204)
async def read_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
                     .values(read_at=func.now()))
    await db.commit()
