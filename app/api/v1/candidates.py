from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_roles
from app.models.candidate import CandidateProfile, CandidateSkill, SkillSource, SkillStatus
from app.models.reference import Skill
from app.models.user import User, UserRole
from app.schemas.candidate import CandidateProfileOut, CandidateProfileUpdate, FSPLinkIn, PrivacyUpdate
from app.domain import grade_policy as gp
from app.services.profile_service import (
    get_candidate_by_user, link_fsp, load_fsp_achievements, refresh_candidate_search_index, unlink_fsp,
)
from app.services.strength_service import recompute_strength

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/me/profile", response_model=CandidateProfileOut)
async def get_my_profile(
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/me/profile", response_model=CandidateProfileOut)
async def update_my_profile(
    body: CandidateProfileUpdate,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field in ("first_name", "last_name", "headline", "city", "remote_ok", "phone", "about"):
        val = getattr(body, field)
        if val is not None:
            setattr(profile, field, val)
    if body.skills is not None:
        existing = await db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == profile.id))
        for cs in existing.scalars().all():
            await db.delete(cs)
        for name in body.skills:
            slug = name.lower().strip()
            res = await db.execute(select(Skill).where(Skill.slug == slug))
            skill = res.scalar_one_or_none()
            if not skill:
                skill = Skill(name=name, slug=slug)
                db.add(skill)
                await db.flush()
            db.add(
                CandidateSkill(
                    candidate_id=profile.id,
                    skill_id=skill.id,
                    source=SkillSource.self_declared,
                    status=SkillStatus.claimed,
                )
            )
    await refresh_candidate_search_index(db, profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = body.model_dump()
    profile.is_discoverable = data.pop("is_discoverable")       # видимость в банке хранится отдельным полем
    profile.privacy = {**(profile.privacy or {}), **data}
    await db.commit()
    return {**profile.privacy, "is_discoverable": profile.is_discoverable}


@router.post("/me/fsp-link")
async def fsp_link(
    body: FSPLinkIn,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    link = await link_fsp(db, profile, body.external_id)
    achievements = await load_fsp_achievements(db, profile)
    await recompute_strength(db, profile)            # сила профиля пересчитывается по формуле, а не «+10»
    await refresh_candidate_search_index(db, profile)
    await db.commit()
    return {
        "linked": bool(body.external_id),
        "external_id": link.external_id,
        "has_history": bool(achievements),          # False — корректный случай: «истории ФСП нет»
        "achievements": [
            {"title": a.title, "event_name": a.event_name, "rank": a.rank, "event_date": a.event_date} for a in achievements
        ],
    }


@router.delete("/me/fsp-link", status_code=204)
async def fsp_unlink(user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await unlink_fsp(db, profile)
    await recompute_strength(db, profile)
    await db.commit()


@router.get("/me/category")
async def my_category(user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    profile = await get_candidate_by_user(db, user.id)
    if not profile or not profile.category_id:
        return {"category": None, "onboarding_completed": profile.onboarding_completed if profile else False}
    await db.refresh(profile, ["category"])
    return {
        "category": {"id": profile.category.id, "label": profile.category.label, "slug": profile.category.slug},
        "profile_strength": profile.profile_strength,
        "onboarding_completed": profile.onboarding_completed,
        "confirmed_grade_id": profile.confirmed_grade_id,
        "verification_status": gp.verification_status(datetime.now(timezone.utc), profile.grade_valid_until),
        "valid_until": profile.grade_valid_until,
        "grade_last_changed_at": profile.grade_last_changed_at,
    }
