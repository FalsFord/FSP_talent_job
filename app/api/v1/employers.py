import random
import re
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1._common import employer_profile as _employer_profile
from app.api.v1._common import matched_out
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.domain import grade_policy as gp
from app.models.candidate import CandidateProfile, CandidateSkill, Category
from app.models.employer import EmployerNeed, WorkFormat
from app.models.fsp import FSPParticipantLink
from app.models.platform import ShortlistSnapshot
from app.models.reference import Grade
from app.models.user import User, UserRole
from app.schemas.candidate import CandidatePublicOut
from app.schemas.employer import (
    CompanyOut, CompanyUpdate, MatchedCandidateOut, NeedCreate, NeedOut, ShortlistIn, ShortlistOut, TaskPreviewIn,
    CategoryRecommendation,
)
from app.services import task_service
from app.services.matching_service import (
    contacts_for, create_need, display_name, rank_candidates_for_need, recommended_categories, revealed_candidate_ids,
    save_snapshot,
)
from datetime import datetime, timezone

router = APIRouter(prefix="/employers", tags=["employers"])


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


async def _own_need(db: AsyncSession, ep, need_id: UUID) -> EmployerNeed:
    need = await db.get(EmployerNeed, need_id)
    if not need or need.employer_id != ep.id:
        raise HTTPException(status_code=404, detail="Need not found")
    return need


@router.get("/needs/{need_id}/candidates", response_model=list[MatchedCandidateOut])
async def need_candidates(need_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                          db: AsyncSession = Depends(get_db)):
    """Совместимый эндпоинт: быстрая подборка без фильтров (снимок не сохраняется)."""
    ep = await _employer_profile(db, user.id)
    need = await _own_need(db, ep, need_id)
    revealed = await revealed_candidate_ids(db, ep.id)
    return [matched_out(r, revealed) for r in await rank_candidates_for_need(db, need)]


@router.get("/needs/{need_id}/categories", response_model=list[CategoryRecommendation])
async def need_categories(need_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                          db: AsyncSession = Depends(get_db)):
    """Рекомендованные категории (специализация × грейд) с числом кандидатов (ТЗ, работа с подборкой)."""
    ep = await _employer_profile(db, user.id)
    return await recommended_categories(db, await _own_need(db, ep, need_id))


@router.post("/needs/{need_id}/shortlist", response_model=ShortlistOut)
async def build_shortlist(need_id: UUID, body: ShortlistIn, user: User = Depends(require_roles(UserRole.employer)),
                          db: AsyncSession = Depends(get_db)):
    """Подборка с фильтрами и объяснением. Каждое уточнение фильтров сохраняется отдельным снимком —
    ранее полученная подборка не теряется (ТЗ, «Функциональные требования к поиску и подбору»)."""
    ep = await _employer_profile(db, user.id)
    need = await _own_need(db, ep, need_id)
    filters = body.filters.model_dump(exclude_none=True)
    revealed = await revealed_candidate_ids(db, ep.id)
    cands = [matched_out(r, revealed) for r in await rank_candidates_for_need(db, need, limit=body.limit, filters=filters)]
    cats = await recommended_categories(db, need)
    snap = await save_snapshot(db, need, jsonable_encoder(filters), jsonable_encoder([c.model_dump() for c in cands]))
    await db.commit()
    return ShortlistOut(snapshot_id=snap.id, filters=filters, categories=cats, candidates=cands)


@router.get("/needs/{need_id}/shortlist/snapshots")
async def list_snapshots(need_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                         db: AsyncSession = Depends(get_db)):
    ep = await _employer_profile(db, user.id)
    need = await _own_need(db, ep, need_id)
    rows = (await db.execute(select(ShortlistSnapshot).where(ShortlistSnapshot.need_id == need.id)
                             .order_by(ShortlistSnapshot.created_at.desc()).limit(50))).scalars().all()
    return [{"id": r.id, "created_at": r.created_at, "filters": r.filters, "count": len(r.results)} for r in rows]


@router.get("/needs/{need_id}/shortlist/snapshots/{snapshot_id}", response_model=ShortlistOut)
async def get_snapshot(need_id: UUID, snapshot_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                       db: AsyncSession = Depends(get_db)):
    ep = await _employer_profile(db, user.id)
    need = await _own_need(db, ep, need_id)
    snap = await db.get(ShortlistSnapshot, snapshot_id)
    if not snap or snap.need_id != need.id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return ShortlistOut(snapshot_id=snap.id, filters=snap.filters, categories=await recommended_categories(db, need),
                        candidates=[MatchedCandidateOut(**c) for c in snap.results])


_LANG_HINTS = {"sql": ("sql", "postgres", "mysql", "запрос"), "java": ("java", "spring", "kotlin"),
               "python": ("python", "django", "fastapi", "flask", "pytest")}


@router.post("/needs/{need_id}/task-preview")
async def task_preview(need_id: UUID, body: TaskPreviewIn, user: User = Depends(require_roles(UserRole.employer)),
                       db: AsyncSession = Depends(get_db)):
    """Демонстрация RAG-конвейера: из описания потребности (вакансии) формируется набор заданий.
    Показывает условия и происхождение контекста (какие материалы корпуса повлияли), но не ключи/тесты."""
    ep = await _employer_profile(db, user.id)
    need = await _own_need(db, ep, need_id)
    text = f"{need.title} {need.description} {' '.join(need.skills or [])}".lower()
    lang = body.language or max(_LANG_HINTS, key=lambda l: sum(text.count(k) for k in _LANG_HINTS[l]))
    grade = body.grade
    if not grade:
        g = await db.get(Grade, need.grade_id) if need.grade_id else None
        grade = g.code if g else "middle"
    seed = body.seed if body.seed is not None else secrets.randbits(31)
    langs = [lang] if lang == "sql" else [lang, "sql"]
    specs, prov = await task_service.compose_specs(db, seed=seed, grade=grade, languages=langs, spec_name=need.title,
                                                    purpose="preview", n_items=body.n_items, recent=set(), extra_text=text[:600])
    return {"language": lang, "grade": grade, "seed": seed, "provenance": prov,
            "tasks": [{**s.public_dict(), "generator_id": s.generator_id, "sources": s.sources} for s in specs]}


@router.get("/candidates/{candidate_id}/contacts")
async def candidate_contacts(candidate_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                             db: AsyncSession = Depends(get_db)):
    """Контакты доступны ТОЛЬКО после принятия приглашения или собственного отклика (ТЗ п.2.2)."""
    ep = await _employer_profile(db, user.id)
    c = await db.get(CandidateProfile, candidate_id)
    contacts = await contacts_for(db, ep.id, c) if c else None
    if contacts is None:
        raise DomainError("CONTACTS_LOCKED", "Контакты откроются после того, как кандидат примет приглашение", 403)
    return {"candidate_id": candidate_id, "contacts": contacts}


@router.get("/candidates/{candidate_id}/preview", response_model=CandidatePublicOut)
async def preview_candidate(candidate_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                            db: AsyncSession = Depends(get_db)):
    ep = await _employer_profile(db, user.id)
    result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == candidate_id, CandidateProfile.onboarding_completed == True,  # noqa: E712
                                       CandidateProfile.is_discoverable == True)  # noqa: E712
        .options(selectinload(CandidateProfile.category),
                 selectinload(CandidateProfile.skills).selectinload(CandidateSkill.skill),
                 selectinload(CandidateProfile.fsp_link).selectinload(FSPParticipantLink.achievements)))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    contacts = await contacts_for(db, ep.id, c)
    ach = c.fsp_link.achievements if c.fsp_link and c.fsp_link.achievements else []
    return CandidatePublicOut(
        id=c.id, display_name=display_name(c, contacts is not None), headline=c.headline,
        category_label=c.category.label if c.category else None, profile_strength=c.profile_strength,
        skills=[cs.skill.name for cs in c.skills if cs.skill], fsp_achievements_count=len(ach),
        contacts_hidden=contacts is None, phone=contacts["phone"] if contacts else None,
        email=contacts["email"] if contacts else None,
        verification_status=gp.verification_status(datetime.now(timezone.utc), c.grade_valid_until),
        grade_valid_until=c.grade_valid_until,
        verified_skills=[cs.skill.name for cs in c.skills if cs.skill and cs.status.value == "verified"],
        fsp_achievements=[{"title": a.title, "event_name": a.event_name, "rank": a.rank, "event_date": a.event_date} for a in ach],
        fsp_linked=c.fsp_link is not None)
