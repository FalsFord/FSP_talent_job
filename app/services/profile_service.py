import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import CandidateProfile, CandidateSkill
from app.models.fsp import FSPAchievement, FSPParticipantLink
from app.models.reference import Grade, Specialization
from app.search.embedding import build_candidate_search_text, embed_text


async def get_candidate_by_user(db: AsyncSession, user_id: uuid.UUID) -> CandidateProfile | None:
    result = await db.execute(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(selectinload(CandidateProfile.skills).selectinload(CandidateSkill.skill))
    )
    return result.scalar_one_or_none()


async def refresh_candidate_search_index(db: AsyncSession, profile: CandidateProfile) -> None:
    result = await db.execute(
        select(CandidateSkill)
        .where(CandidateSkill.candidate_id == profile.id)
        .options(selectinload(CandidateSkill.skill))
    )
    skills = [cs.skill.name for cs in result.scalars().all() if cs.skill]
    spec_name = None
    grade_name = None
    if profile.specialization_id:
        spec = await db.get(Specialization, profile.specialization_id)
        spec_name = spec.name if spec else None
    if profile.confirmed_grade_id:
        grade = await db.get(Grade, profile.confirmed_grade_id)
        grade_name = grade.name if grade else None
    text = build_candidate_search_text(profile, skills, grade_name, spec_name)
    profile.search_text = text
    profile.embedding = embed_text(text)


async def link_fsp(db: AsyncSession, profile: CandidateProfile, external_id: str | None) -> FSPParticipantLink:
    """Связывает профиль с ID участника ФСП и подтягивает достижения через провайдера (mock или реальный)."""
    from app.integrations.fsp import get_provider

    result = await db.execute(
        select(FSPParticipantLink).where(FSPParticipantLink.candidate_id == profile.id)
        .options(selectinload(FSPParticipantLink.achievements))
    )
    link = result.scalar_one_or_none()
    if not link:
        link = FSPParticipantLink(candidate_id=profile.id, external_id=external_id)
        db.add(link)
        await db.flush()
        await db.refresh(link, ["achievements"])
    elif link.external_id != external_id:
        link.external_id = external_id
        for a in list(link.achievements):
            await db.delete(a)
        await db.flush()
        await db.refresh(link, ["achievements"])
    if external_id and not link.achievements:
        for a in await get_provider().fetch_achievements(external_id):
            db.add(FSPAchievement(link_id=link.id, **a))
        await db.flush()
    return link


async def unlink_fsp(db: AsyncSession, profile: CandidateProfile) -> None:
    result = await db.execute(select(FSPParticipantLink).where(FSPParticipantLink.candidate_id == profile.id))
    link = result.scalar_one_or_none()
    if link:
        await db.delete(link)
        await db.flush()


async def load_fsp_achievements(db: AsyncSession, profile: CandidateProfile) -> list[FSPAchievement]:
    result = await db.execute(
        select(FSPParticipantLink).where(FSPParticipantLink.candidate_id == profile.id)
        .options(selectinload(FSPParticipantLink.achievements))
    )
    link = result.scalar_one_or_none()
    return list(link.achievements) if link else []
