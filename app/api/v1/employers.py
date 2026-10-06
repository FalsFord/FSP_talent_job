from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_roles
from app.models.candidate import CandidateProfile, CandidateSkill, Category
from app.models.employer import EmployerNeed, EmployerProfile, WorkFormat
from app.models.fsp import FSPParticipantLink
from app.models.user import User, UserRole
from app.schemas.candidate import CandidatePublicOut
from app.schemas.employer import CompanyOut, CompanyUpdate, MatchedCandidateOut, MatchExplanation, NeedCreate, NeedOut
from app.services.matching_service import create_need, rank_candidates_for_need

router = APIRouter(prefix="/employers", tags=["employers"])


async def _employer_profile(db: AsyncSession, user_id: UUID) -> EmployerProfile:
    result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id).options(selectinload(EmployerProfile.company))
    )
    ep = result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Employer profile not found")
    return ep


@router.get("/me/company", response_model=CompanyOut)
async def get_company(user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await _employer_profile(db, user.id)
    return ep.company


@router.patch("/me/company", response_model=CompanyOut)
async def update_company(
    body: CompanyUpdate,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    ep = await _employer_profile(db, user.id)
    for field in ("name", "description", "website", "industry"):
        val = getattr(body, field)
        if val is not None:
            setattr(ep.company, field, val)
    await db.commit()
    await db.refresh(ep.company)
    return ep.company


@router.post("/needs", response_model=NeedOut, status_code=201)
async def create_employer_need(
    body: NeedCreate,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    ep = await _employer_profile(db, user.id)
    wf = WorkFormat(body.work_format) if body.work_format else None
    need = await create_need(
        db,
        ep,
        {
            "title": body.title,
            "description": body.description,
            "specialization_id": body.specialization_id,
            "grade_id": body.grade_id,
            "skills": body.skills,
            "work_format": wf,
            "salary_min": body.salary_min,
            "salary_max": body.salary_max,
        },
    )
    await db.commit()
    await db.refresh(need)
    return need


@router.get("/needs", response_model=list[NeedOut])
async def list_needs(user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await _employer_profile(db, user.id)
    result = await db.execute(select(EmployerNeed).where(EmployerNeed.employer_id == ep.id).order_by(EmployerNeed.created_at.desc()))
    return list(result.scalars().all())


@router.get("/needs/{need_id}/candidates", response_model=list[MatchedCandidateOut])
async def need_candidates(
    need_id: UUID,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    ep = await _employer_profile(db, user.id)
    need = await db.get(EmployerNeed, need_id)
    if not need or need.employer_id != ep.id:
        raise HTTPException(status_code=404, detail="Need not found")
    ranked = await rank_candidates_for_need(db, need)
    out = []
    for row in ranked:
        c: CandidateProfile = row["candidate"]
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or "Кандидат"
        cat_label = c.category.label if c.category else None
        out.append(
            MatchedCandidateOut(
                candidate_id=c.id,
                display_name=name,
                category_label=cat_label,
                match_score=row["match_score"],
                explanation=MatchExplanation(**row["explanation"]),
                contacts_hidden=True,
            )
        )
    return out


@router.get("/candidates/{candidate_id}/preview", response_model=CandidatePublicOut)
async def preview_candidate(
    candidate_id: UUID,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CandidateProfile)
        .where(CandidateProfile.id == candidate_id, CandidateProfile.onboarding_completed == True)  # noqa: E712
        .options(
            selectinload(CandidateProfile.category),
            selectinload(CandidateProfile.skills).selectinload(CandidateSkill.skill),
            selectinload(CandidateProfile.fsp_link).selectinload(FSPParticipantLink.achievements),
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    skills = [cs.skill.name for cs in c.skills if cs.skill]
    fsp_count = len(c.fsp_link.achievements) if c.fsp_link and c.fsp_link.achievements else 0
    return CandidatePublicOut(
        id=c.id,
        display_name=f"{c.first_name or ''} {c.last_name or ''}".strip() or "Кандидат",
        headline=c.headline,
        category_label=c.category.label if c.category else None,
        profile_strength=c.profile_strength,
        skills=skills,
        fsp_achievements_count=fsp_count,
        contacts_hidden=True,
    )
