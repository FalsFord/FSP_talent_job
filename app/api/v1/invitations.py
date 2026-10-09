"""Приглашения: инициатива у работодателя (ТЗ). Кандидат видит условия (зарплата, компания, способ связи) ДО общения;
контакты кандидата раскрываются работодателю только после принятия."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import candidate_profile, employer_profile
from app.core.deps import get_current_user, get_db, require_roles
from app.core.errors import DomainError
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerProfile
from app.models.invitation import Invitation, InvitationStatus
from app.models.platform import InvitationEvent
from app.models.user import User, UserRole
from app.schemas.invitation import InvitationCreate, InvitationEventOut, InvitationOut, InvitationStatusUpdate
from app.services import invitation_service as svc
from app.services.matching_service import contacts_for, display_name

router = APIRouter(prefix="/invitations", tags=["invitations"])


async def _render(db: AsyncSession, inv: Invitation, role: str, cache: dict) -> InvitationOut:
    ep = cache.get(("ep", inv.employer_id)) or await db.get(EmployerProfile, inv.employer_id)
    cache[("ep", inv.employer_id)] = ep
    company = cache.get(("co", ep.company_id)) or await db.get(Company, ep.company_id)
    cache[("co", ep.company_id)] = company
    euser = cache.get(("u", ep.user_id)) or await db.get(User, ep.user_id)
    cache[("u", ep.user_id)] = euser
    cand = cache.get(("c", inv.candidate_id)) or await db.get(CandidateProfile, inv.candidate_id)
    cache[("c", inv.candidate_id)] = cand
    accepted = inv.status == InvitationStatus.accepted
    out = InvitationOut(
        id=inv.id, title=inv.title, message=inv.message, salary_min=inv.salary_min, salary_max=inv.salary_max,
        status=inv.status.value, company_name=company.name if company else None,
        company_contact=inv.contact_method or (euser.email if euser else None), vacancy_id=inv.vacancy_id,
        created_at=inv.created_at, expires_at=inv.expires_at, viewed_at=inv.viewed_at, decided_at=inv.decided_at)
    if role == "employer":
        out.candidate_display = display_name(cand, accepted)
        if accepted:      # контакты — только по таблице contact_reveals (единственный источник права)
            out.candidate_contacts = await contacts_for(db, inv.employer_id, cand)
    return out


async def _load(db: AsyncSession, user: User, invitation_id: UUID):
    inv = await db.get(Invitation, invitation_id)
    if not inv:
        raise DomainError("NOT_FOUND", "Invitation not found", 404)
    if user.role == UserRole.employer:
        ep = await employer_profile(db, user.id)
        if inv.employer_id != ep.id:
            raise DomainError("NOT_FOUND", "Invitation not found", 404)
        return inv, "employer"
    if user.role == UserRole.candidate:
        c = await candidate_profile(db, user.id)
        if inv.candidate_id != c.id:
            raise DomainError("NOT_FOUND", "Invitation not found", 404)
        return inv, "candidate"
    raise DomainError("FORBIDDEN", "Insufficient permissions", 403)


@router.post("", response_model=InvitationOut, status_code=201)
async def create_invitation(body: InvitationCreate, user: User = Depends(require_roles(UserRole.employer)),
                            db: AsyncSession = Depends(get_db),
                            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64)):
    ep = await employer_profile(db, user.id)
    inv = await svc.create_invitation(db, ep, user, body.model_dump(), idempotency_key)
    await db.commit()
    return await _render(db, inv, "employer", {})


@router.get("/sent", response_model=list[InvitationOut])
async def sent(user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    if await svc.expire_stale(db):
        await db.commit()
    rows = (await db.execute(select(Invitation).where(Invitation.employer_id == ep.id)
                             .order_by(Invitation.created_at.desc()))).scalars().all()
    cache: dict = {}
    return [await _render(db, i, "employer", cache) for i in rows]


@router.get("/received", response_model=list[InvitationOut])
async def received(user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    if await svc.expire_stale(db):
        await db.commit()
    rows = (await db.execute(select(Invitation).where(Invitation.candidate_id == c.id)
                             .order_by(Invitation.created_at.desc()))).scalars().all()
    cache: dict = {}
    return [await _render(db, i, "candidate", cache) for i in rows]


@router.get("/{invitation_id}", response_model=InvitationOut)
async def get_invitation(invitation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    inv, role = await _load(db, user, invitation_id)
    if role == "candidate" and inv.status == InvitationStatus.sent:     # открытие карточки = «просмотрено»
        await svc.transition(db, inv, "viewed", "candidate", user.id)
        await db.commit()
    return await _render(db, inv, role, {})


@router.get("/{invitation_id}/events", response_model=list[InvitationEventOut])
async def events(invitation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    inv, _ = await _load(db, user, invitation_id)
    rows = (await db.execute(select(InvitationEvent).where(InvitationEvent.invitation_id == inv.id)
                             .order_by(InvitationEvent.created_at))).scalars().all()
    return [InvitationEventOut(from_status=e.from_status, to_status=e.to_status, actor=e.actor, created_at=e.created_at) for e in rows]


async def _act(db: AsyncSession, user: User, invitation_id: UUID, new_status: str, actor: str) -> InvitationOut:
    inv, role = await _load(db, user, invitation_id)
    if role != actor:
        raise DomainError("FORBIDDEN", "Это действие недоступно для вашей роли", 403)
    await svc.transition(db, inv, new_status, actor, user.id)
    await db.commit()
    return await _render(db, inv, role, {})


@router.post("/{invitation_id}/accept", response_model=InvitationOut)
async def accept(invitation_id: UUID, user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, invitation_id, "accepted", "candidate")


@router.post("/{invitation_id}/decline", response_model=InvitationOut)
async def decline(invitation_id: UUID, user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, invitation_id, "declined", "candidate")


@router.post("/{invitation_id}/withdraw", response_model=InvitationOut)
async def withdraw(invitation_id: UUID, user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, invitation_id, "withdrawn", "employer")


@router.patch("/{invitation_id}", response_model=InvitationOut)
async def update_status(invitation_id: UUID, body: InvitationStatusUpdate, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Совместимый эндпоинт. Кандидат: viewed/accepted/declined. Работодатель: только withdrawn
    (отметить «просмотрено» за кандидата нельзя; такой запрос игнорируется без ошибки)."""
    inv, role = await _load(db, user, invitation_id)
    if role == "employer":
        if body.status == "viewed":
            return await _render(db, inv, role, {})
        if body.status != "withdrawn":
            raise DomainError("FORBIDDEN", "Работодатель может только отозвать приглашение", 403)
    elif body.status == "withdrawn":
        raise DomainError("FORBIDDEN", "Кандидат не может отозвать приглашение", 403)
    await svc.transition(db, inv, body.status, role, user.id)
    await db.commit()
    return await _render(db, inv, role, {})
