import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import CandidateProfile, CandidateSkill, Category
from app.models.employer import EmployerNeed, EmployerProfile
from app.models.fsp import FSPParticipantLink
from app.models.reference import Grade, Specialization
from app.search.embedding import embed_text
from app.search.hybrid import compute_match_score, cosine_similarity, keyword_overlap, skill_jaccard


async def create_need(db: AsyncSession, employer: EmployerProfile, data: dict) -> EmployerNeed:
    need = EmployerNeed(employer_id=employer.id, **data)
    text = f"{need.title} {need.description} {' '.join(need.skills or [])}"
    need.search_text = text
    need.embedding = embed_text(text)
    db.add(need)
    await db.flush()
    return need


async def rank_candidates_for_need(db: AsyncSession, need: EmployerNeed, limit: int = 50) -> list[dict]:
    query = (
        select(CandidateProfile)
        .where(CandidateProfile.onboarding_completed == True)  # noqa: E712
        .options(
            selectinload(CandidateProfile.category).selectinload(Category.specialization),
            selectinload(CandidateProfile.category).selectinload(Category.grade),
            selectinload(CandidateProfile.skills).selectinload(CandidateSkill.skill),
            selectinload(CandidateProfile.fsp_link).selectinload(FSPParticipantLink.achievements),
        )
    )
    if need.specialization_id:
        query = query.where(CandidateProfile.specialization_id == need.specialization_id)
    result = await db.execute(query)
    candidates = list(result.scalars().all())

    need_vec = need.embedding or embed_text(need.search_text or need.description)
    need_skills = need.skills or []
    need_grade = await db.get(Grade, need.grade_id) if need.grade_id else None

    ranked: list[dict] = []
    for c in candidates:
        if need.work_format and need.work_format.value == "remote" and not c.remote_ok:
            continue
        c_skills = [cs.skill.name for cs in c.skills if cs.skill]
        sem = cosine_similarity(need_vec, list(c.embedding or []))
        kw = keyword_overlap(need.search_text or "", c.search_text or "")
        grade_match = bool(need_grade and c.confirmed_grade_id == need_grade.id)
        if need_grade and not grade_match:
            cg = await db.get(Grade, c.confirmed_grade_id) if c.confirmed_grade_id else None
            if cg and abs(cg.level - need_grade.level) > 1:
                continue
        sj = skill_jaccard(need_skills, c_skills)
        fsp_count = len(c.fsp_link.achievements) if c.fsp_link and c.fsp_link.achievements else 0
        fsp_boost = min(fsp_count * 0.15, 0.45)
        score = compute_match_score(
            semantic=sem,
            keyword=kw,
            grade_match=grade_match,
            skill_j=sj,
            profile_strength=c.profile_strength,
            fsp_boost=fsp_boost,
        )
        matched = [s for s in need_skills if s.lower() in {x.lower() for x in c_skills}]
        missing = [s for s in need_skills if s.lower() not in {x.lower() for x in c_skills}]
        ranked.append(
            {
                "candidate": c,
                "match_score": score,
                "explanation": {
                    "semantic": round(sem, 3),
                    "keyword": round(kw, 3),
                    "grade_match": grade_match,
                    "skills_matched": matched,
                    "skills_missing": missing,
                    "profile_strength": c.profile_strength,
                    "fsp_achievements_count": fsp_count,
                },
            }
        )

    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return ranked[:limit]


async def search_candidates(
    db: AsyncSession,
    query_text: str,
    specialization_id: uuid.UUID | None,
    grade_id: uuid.UUID | None,
    has_fsp: bool | None,
    limit: int = 30,
) -> list[dict]:
    fake_need = EmployerNeed(
        employer_id=uuid.uuid4(),
        title=query_text,
        description=query_text,
        specialization_id=specialization_id,
        grade_id=grade_id,
        skills=[],
    )
    fake_need.search_text = query_text
    fake_need.embedding = embed_text(query_text)
    ranked = await rank_candidates_for_need(db, fake_need, limit=100)
    if has_fsp is True:
        ranked = [r for r in ranked if r["explanation"]["fsp_achievements_count"] > 0]
    elif has_fsp is False:
        ranked = [r for r in ranked if r["explanation"]["fsp_achievements_count"] == 0]
    return ranked[:limit]
