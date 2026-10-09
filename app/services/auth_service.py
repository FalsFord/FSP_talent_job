import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import DomainError
from app.models.platform import EmailToken
from app.models.user import User
from app.services.mail_service import send_mail


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_verification(db: AsyncSession, user: User) -> str:
    """Создаёт токен подтверждения (в БД хранится только хеш), отправляет письмо. Возвращает «сырой» токен."""
    raw = secrets.token_urlsafe(32)
    db.add(EmailToken(user_id=user.id, purpose="verify", token_hash=_hash(raw),
                      expires_at=datetime.now(timezone.utc) + timedelta(hours=48)))
    await db.flush()
    link = f"{settings.frontend_url.rstrip('/')}/verify-email?token={raw}"
    await send_mail(user.email, "Подтверждение e-mail — FSP Talent Platform",
                    f"Для завершения регистрации перейдите по ссылке (действует 48 часов):\n{link}\n")
    return raw


async def verify_token(db: AsyncSession, raw: str) -> User:
    res = await db.execute(select(EmailToken).where(EmailToken.token_hash == _hash(raw), EmailToken.purpose == "verify"))
    tok = res.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not tok or tok.used_at is not None or tok.expires_at < now:
        raise DomainError("INVALID_OR_EXPIRED_TOKEN", "Ссылка недействительна или устарела", 400)
    user = await db.get(User, tok.user_id)
    if not user:
        raise DomainError("INVALID_OR_EXPIRED_TOKEN", "Ссылка недействительна или устарела", 400)
    tok.used_at = now
    user.email_verified = True
    await db.flush()
    return user
