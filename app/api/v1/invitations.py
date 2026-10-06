from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, require_roles
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User, UserRole
from app.schemas.invitation import InvitationCreate, InvitationOut, InvitationStatusUpdate

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("", response_model=InvitationOut, status_code=201)
async def create_invitation(
    body: InvitationCreate,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    if body.salary_max < body.salary_min:
        raise HTTPException(status_code=422, detail="salary_max must be >= salary_min")
    ep_result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user.id).options(selectinload(EmployerProfile.company))
    )
    ep = ep_result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Employer not found")
    candidate = await db.get(CandidateProfile, body.candidate_id)
    if not candidate or not candidate.onboarding_completed:
        raise HTTPException(status_code=404, detail="Candidate not available")
    inv = Invitation(
        employer_id=ep.id,
        candidate_id=candidate.id,
        vacancy_id=body.vacancy_id,
        title=body.title,
        message=body.message,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
        status=InvitationStatus.sent,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return InvitationOut(
        id=inv.id,
        title=inv.title,
        message=inv.message,
        salary_min=inv.salary_min,
        salary_max=inv.salary_max,
        status=inv.status.value,
        company_name=ep.company.name,
    )


@router.get("/sent", response_model=list[InvitationOut])
async def sent_invitations(user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep_result = await db.execute(select(EmployerProfile).where(EmployerProfile.user_id == user.id))
    ep = ep_result.scalar_one_or_none()
    if not ep:
        return []
    result = await db.execute(
        select(Invitation)
        .where(Invitation.employer_id == ep.id)
        .options(selectinload(Invitation.candidate), selectinload(Invitation.employer).selectinload(EmployerProfile.company))
    )
    out = []
    for inv in result.scalars().all():
        contacts = None
        if inv.status == InvitationStatus.accepted:
            c = inv.candidate
            cu = await db.get(User, c.user_id)
            contacts = {"email": cu.email if cu else None, "phone": c.phone}
        out.append(
            InvitationOut(
                id=inv.id,
                title=inv.title,
                message=inv.message,
                salary_min=inv.salary_min,
                salary_max=inv.salary_max,
                status=inv.status.value,
                company_name=inv.employer.company.name,
                candidate_display=f"{inv.candidate.first_name} {inv.candidate.last_name}",
                candidate_contacts=contacts,
            )
        )
    return out


@router.get("/received", response_model=list[InvitationOut])
async def received_invitations(
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return []
    result = await db.execute(
        select(Invitation)
        .where(Invitation.candidate_id == profile.id)
        .options(selectinload(Invitation.employer).selectinload(EmployerProfile.company))
    )
    return [
        InvitationOut(
            id=inv.id,
            title=inv.title,
            message=inv.message,
            salary_min=inv.salary_min,
            salary_max=inv.salary_max,
            status=inv.status.value,
            company_name=inv.employer.company.name,
        )
        for inv in result.scalars().all()
    ]


@router.patch("/{invitation_id}", response_model=InvitationOut)
async def update_invitation_status(
    invitation_id: UUID,
    body: InvitationStatusUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Invitation, invitation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    # candidate can accept/decline/view; employer can view only
    profile_result = await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    profile = profile_result.scalar_one_or_none()
    if profile and profile.id == inv.candidate_id:
        inv.status = InvitationStatus(body.status)
    else:
        ep_result = await db.execute(select(EmployerProfile).where(EmployerProfile.user_id == user.id))
        ep = ep_result.scalar_one_or_none()
        if not ep or ep.id != inv.employer_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if body.status != "viewed":
            raise HTTPException(status_code=403, detail="Employer cannot change to this status")
        inv.status = InvitationStatus.viewed
    await db.commit()
    await db.refresh(inv)
    ep_result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.id == inv.employer_id).options(selectinload(EmployerProfile.company))
    )
    ep = ep_result.scalar_one()
    return InvitationOut(
        id=inv.id,
        title=inv.title,
        message=inv.message,
        salary_min=inv.salary_min,
        salary_max=inv.salary_max,
        status=inv.status.value,
        company_name=ep.company.name,
    )
