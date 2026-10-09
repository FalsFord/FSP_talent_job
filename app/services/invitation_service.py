"""Приглашения работодателя (смысловой центр ТЗ). Бизнес-правила:
  * зарплата «от–до» в рублях обязательна; кандидат видит условия до начала общения;
  * статусы: sent → viewed → accepted/declined (кандидат), withdrawn (работодатель), expired (система);
  * контакты кандидата раскрываются только после accepted (запись в contact_reveals);
  * защита от спама: дневной лимит (строже для новых аккаунтов) и пауза на пару «работодатель–кандидат»;
  * идемпотентное создание по заголовку Idempotency-Key."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import DomainError
from app.domain import invitation_fsm as fsm
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerProfile
from app.models.invitation import Invitation, InvitationStatus
from app.models.platform import ContactReveal, InvitationEvent
from app.models.user import User
from app.models.vacancy import Vacancy
from app.services.notification_service import notify


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_invitation(db: AsyncSession, employer: EmployerProfile, employer_user: User, data: dict,
                            idempotency_key: str | None) -> Invitation:
    if idempotency_key:
        existing = (await db.execute(select(Invitation).where(Invitation.employer_id == employer.id,
                                                              Invitation.idempotency_key == idempotency_key))).scalar_one_or_none()
        if existing:
            return existing                       # повтор запроса — тот же результат, дубля нет
    err = fsm.validate_salary(data.get("salary_min"), data.get("salary_max"))
    if err:
        raise DomainError(err, {"SALARY_REQUIRED": "Укажите зарплату «от–до» в рублях",
                                "SALARY_INVALID": "Зарплата: «от» > 0 и «до» не меньше «от»",
                                "SALARY_UNREALISTIC": "Слишком большая зарплата"}[err], 422)
    cand = await db.get(CandidateProfile, data["candidate_id"])
    if not cand or not cand.onboarding_completed or not cand.is_discoverable:
        raise DomainError("CANDIDATE_UNAVAILABLE", "Кандидат недоступен для приглашений", 404)
    if data.get("vacancy_id"):
        vac = await db.get(Vacancy, data["vacancy_id"])
        if not vac or vac.employer_id != employer.id:
            raise DomainError("VACANCY_NOT_FOUND", "Вакансия не найдена", 404)
    now = _now()
    sent_24h = (await db.execute(select(func.count()).select_from(Invitation).where(
        Invitation.employer_id == employer.id, Invitation.created_at >= now - timedelta(hours=24)))).scalar_one()
    last = (await db.execute(select(func.max(Invitation.created_at)).where(
        Invitation.employer_id == employer.id, Invitation.candidate_id == cand.id,
        Invitation.status != InvitationStatus.withdrawn))).scalar_one()
    age_days = (now - employer_user.created_at).days if employer_user.created_at else 365
    lim = fsm.check_invite_limits(now, sent_last_24h=sent_24h, per_day=settings.invitations_per_day,
                                  last_invite_to_candidate=last, pair_cooldown_days=settings.invitation_pair_cooldown_days,
                                  account_age_days=age_days)
    if lim:
        raise DomainError(lim, "Достигнут дневной лимит приглашений" if lim == "INVITE_LIMIT"
                          else "Этому кандидату уже отправлялось приглашение недавно", 429 if lim == "INVITE_LIMIT" else 409)
    inv = Invitation(employer_id=employer.id, candidate_id=cand.id, vacancy_id=data.get("vacancy_id"), title=data["title"],
                     message=data["message"], contact_method=data.get("contact_method"), salary_min=data["salary_min"], salary_max=data["salary_max"],
                     status=InvitationStatus.sent, idempotency_key=idempotency_key,
                     expires_at=now + timedelta(days=settings.invitation_ttl_days))
    db.add(inv)
    await db.flush()
    db.add(InvitationEvent(invitation_id=inv.id, from_status=None, to_status="sent", actor="employer", actor_user_id=employer_user.id))
    company_obj = await db.get(Company, employer.company_id)
    company = company_obj.name if company_obj else "Компания"
    await notify(db, cand.user_id, "invitation_received", "Новое приглашение",
                 f"{company}: {inv.title}, {inv.salary_min:,}–{inv.salary_max:,} ₽".replace(",", " "), {"invitation_id": str(inv.id)})
    return inv


async def transition(db: AsyncSession, inv: Invitation, new_status: str, actor: str, actor_user_id: uuid.UUID | None) -> Invitation:
    """Смена статуса с проверкой автомата. Повтор того же решения кандидата идемпотентен."""
    await db.refresh(inv, with_for_update=True)           # блокировка строки от гонок accept/withdraw
    cur = inv.status.value
    if cur == new_status and new_status in ("viewed", "accepted", "declined", "withdrawn"):
        return inv
    if not fsm.can_transition(cur, new_status, actor):
        raise DomainError("INVALID_TRANSITION", f"Переход «{cur}» → «{new_status}» недопустим", 409)
    now = _now()
    inv.status = InvitationStatus(new_status)
    if new_status == "viewed":
        inv.viewed_at = now
    if new_status in fsm.TERMINAL:
        inv.decided_at = now
    db.add(InvitationEvent(invitation_id=inv.id, from_status=cur, to_status=new_status, actor=actor, actor_user_id=actor_user_id))
    employer = await db.get(EmployerProfile, inv.employer_id)
    cand = await db.get(CandidateProfile, inv.candidate_id)
    if new_status == "accepted":
        exists = (await db.execute(select(ContactReveal.id).where(ContactReveal.candidate_id == inv.candidate_id,
                                                                  ContactReveal.employer_id == inv.employer_id))).first()
        if not exists:
            db.add(ContactReveal(candidate_id=inv.candidate_id, employer_id=inv.employer_id, source="invitation", source_id=inv.id))
    if employer and new_status in ("viewed", "accepted", "declined"):
        titles = {"viewed": "Приглашение просмотрено", "accepted": "Кандидат принял приглашение",
                  "declined": "Кандидат отклонил приглашение"}
        await notify(db, employer.user_id, f"invitation_{new_status}", titles[new_status], inv.title, {"invitation_id": str(inv.id)})
    if cand and new_status in ("withdrawn", "expired"):
        await notify(db, cand.user_id, f"invitation_{new_status}",
                     "Приглашение отозвано" if new_status == "withdrawn" else "Срок приглашения истёк", inv.title,
                     {"invitation_id": str(inv.id)})
    await db.flush()
    return inv


async def expire_stale(db: AsyncSession, limit: int = 500) -> int:
    now = _now()
    rows = (await db.execute(select(Invitation).where(Invitation.status.in_([InvitationStatus.sent, InvitationStatus.viewed]),
                                                      Invitation.expires_at.is_not(None), Invitation.expires_at < now)
                             .limit(limit))).scalars().all()
    for inv in rows:
        await transition(db, inv, "expired", "system", None)
    return len(rows)
