"""Подбор кандидатов (ТЗ, «Функциональные требования к поиску и подбору»).

Конвейер: категории (специализация × подтверждённый грейд) → жёсткие фильтры → кандидаты-претенденты
(векторный поиск pgvector ∪ совпадение навыков) → MatchScore (соответствие потребности) и Strength
(сила подтверждённого профиля: тесты, ФСП, свежесть) → итоговый ранг → объяснение причин.
Выдача строится по категориям из тестирования, а не по самоописанному резюме."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain import grade_policy as gp
from app.domain import ranking as rk
from app.models.candidate import CandidateProfile, CandidateSkill, Category, SkillStatus
from app.models.employer import EmployerNeed, EmployerProfile
from app.models.fsp import FSPParticipantLink
from app.models.platform import ContactReveal, ShortlistSnapshot
from app.models.reference import Grade, Skill
from app.models.user import User
from app.search.embedding import embed_text
from app.search.hybrid import cosine_similarity, keyword_overlap

ALGORITHM_VERSION = "v2"
SKILL_FRESH_DAYS = 120
CANDIDATE_POOL = 300


def _vec(x) -> list[float]:
    return [] if x is None else [float(v) for v in x]


async def create_need(db: AsyncSession, employer: EmployerProfile, data: dict) -> EmployerNeed:
    need = EmployerNeed(employer_id=employer.id, **data)
    text = f"{need.title} {need.description} {' '.join(need.skills or [])}"
    need.search_text = text
    need.embedding = embed_text(text, query=True)
    db.add(need)
    await db.flush()
    return need


def display_name(c: CandidateProfile, revealed: bool) -> str:
    """До принятия приглашения работодатель видит «Имя Ф.»; полное имя — после раскрытия контактов
    или если кандидат сам разрешил (privacy.show_full_name). Контакты скрыты в любом случае (ТЗ п.2.2)."""
    first, last = (c.first_name or "").strip(), (c.last_name or "").strip()
    if revealed or (c.privacy or {}).get("show_full_name"):
        return f"{first} {last}".strip() or "Кандидат"
    return f"{first} {last[:1]}.".strip() if first else "Кандидат"


async def revealed_candidate_ids(db: AsyncSession, employer_id: uuid.UUID) -> set[uuid.UUID]:
    res = await db.execute(select(ContactReveal.candidate_id).where(ContactReveal.employer_id == employer_id))
    return set(res.scalars().all())


async def contacts_for(db: AsyncSession, employer_id: uuid.UUID, c: CandidateProfile) -> dict | None:
    """Контакты кандидата. Единственный источник права — таблица contact_reveals."""
    res = await db.execute(select(ContactReveal.id).where(ContactReveal.employer_id == employer_id,
                                                          ContactReveal.candidate_id == c.id))
    if res.first() is None:
        return None
    user = await db.get(User, c.user_id)
    return {"email": user.email if user else None, "phone": c.phone}


def _skill_map(c: CandidateProfile, now: datetime) -> dict[str, str]:
    out: dict[str, str] = {}
    for cs in c.skills:
        if not cs.skill:
            continue
        st = "declared"
        if cs.status == SkillStatus.verified:
            fresh = cs.verified_at is None or now - cs.verified_at <= timedelta(days=SKILL_FRESH_DAYS)
            st = "verified" if fresh else "stale"
        elif cs.status == SkillStatus.stale:
            st = "stale"
        out[cs.skill.name.lower()] = st
    return out


async def _candidate_pool(db: AsyncSession, need_vec: list[float], need_skills: list[str], f: dict) -> list[CandidateProfile]:
    conds = [CandidateProfile.onboarding_completed == True,  # noqa: E712
             CandidateProfile.is_discoverable == True,  # noqa: E712
             CandidateProfile.confirmed_grade_id.is_not(None)]
    if f.get("specialization_id"):
        conds.append(CandidateProfile.specialization_id == f["specialization_id"])
    if f.get("grade_ids"):
        conds.append(CandidateProfile.confirmed_grade_id.in_(f["grade_ids"]))
    if f.get("city"):
        conds.append(func.lower(CandidateProfile.city) == f["city"].lower())
    ids: set[uuid.UUID] = set()
    if need_vec:
        ids |= set((await db.execute(select(CandidateProfile.id).where(*conds)
                                     .order_by(CandidateProfile.embedding.cosine_distance(need_vec))
                                     .limit(CANDIDATE_POOL))).scalars().all())
    skills_l = [s.lower() for s in need_skills]
    if skills_l:
        ids |= set((await db.execute(
            select(CandidateSkill.candidate_id).join(Skill, Skill.id == CandidateSkill.skill_id)
            .join(CandidateProfile, CandidateProfile.id == CandidateSkill.candidate_id)
            .where(*conds, func.lower(Skill.name).in_(skills_l)).distinct().limit(CANDIDATE_POOL))).scalars().all())
    if not ids:
        return []
    res = await db.execute(select(CandidateProfile).where(CandidateProfile.id.in_(ids)).options(
        selectinload(CandidateProfile.category).selectinload(Category.specialization),
        selectinload(CandidateProfile.category).selectinload(Category.grade),
        selectinload(CandidateProfile.skills).selectinload(CandidateSkill.skill),
        selectinload(CandidateProfile.fsp_link).selectinload(FSPParticipantLink.achievements)))
    return list(res.scalars().all())


async def rank_candidates_for_need(db: AsyncSession, need: EmployerNeed, limit: int = 50,
                                   filters: dict[str, Any] | None = None) -> list[dict]:
    f = dict(filters or {})
    f.setdefault("specialization_id", need.specialization_id)
    now = datetime.now(timezone.utc)
    need_text = need.search_text or f"{need.title} {need.description}"
    need_vec = _vec(need.embedding) or embed_text(need_text, query=True)
    need_skills = list(need.skills or [])
    grades = {g.id: g for g in (await db.execute(select(Grade))).scalars().all()}
    need_grade = grades.get(need.grade_id) if need.grade_id else None
    need_remote = bool(need.work_format and getattr(need.work_format, "value", need.work_format) == "remote")

    out: list[dict] = []
    for c in await _candidate_pool(db, need_vec, need_skills, f):
        cg = grades.get(c.confirmed_grade_id)
        if need_grade and cg and abs(cg.level - need_grade.level) > 1:
            continue
        if need_remote and not c.remote_ok:
            continue
        status = gp.verification_status(now, c.grade_valid_until)
        if f.get("verified_only") and status != "confirmed":
            continue
        skills = _skill_map(c, now)
        ach = c.fsp_link.achievements if c.fsp_link and c.fsp_link.achievements else []
        if f.get("has_fsp") is True and not ach:
            continue
        if f.get("has_fsp") is False and ach:
            continue
        if f.get("skills_all") and not all(s.lower() in skills for s in f["skills_all"]):
            continue
        if f.get("min_strength") is not None and c.profile_strength < f["min_strength"]:
            continue
        sem = cosine_similarity(need_vec, _vec(c.embedding))
        kw = keyword_overlap(need_text, c.search_text or "")
        sk, matched, missing = rk.skills_overlap(need_skills, skills)
        gfit = rk.grade_fit([need_grade.level] if need_grade else [], cg.level if cg else None)
        fsp = rk.fsp_score([{"place": a.rank, "date": a.event_date} for a in ach], now.date())
        match = rk.match_score(semantic=sem, skills=sk if need_skills else 0.5, keyword=kw, grade=gfit, fmt=1.0)
        rank = rk.rank_score(match, c.profile_strength)
        verified = [n for n, s in skills.items() if s == "verified"]
        out.append({
            "candidate": c, "match_score": round(rank, 4), "verification_status": status,
            "explanation": {
                "semantic": round(sem, 3), "keyword": round(kw, 3), "grade_match": gfit >= 1.0,
                "skills_matched": matched, "skills_missing": missing, "profile_strength": c.profile_strength,
                "fsp_achievements_count": len(ach), "rank_score": round(rank, 4), "match_component": round(match, 4),
                "verification_status": status, "skills_verified": verified,
                "reasons": rk.build_reasons(semantic=sem, skills=sk, matched=matched, missing=missing, verified=verified,
                                            grade_fit_v=gfit, fmt_ok=True, fsp=fsp, fsp_count=len(ach), status=status),
            },
        })
    out.sort(key=lambda r: r["match_score"], reverse=True)
    return out[:limit]


async def search_candidates(db: AsyncSession, query_text: str, specialization_id: uuid.UUID | None,
                            grade_id: uuid.UUID | None, has_fsp: bool | None, limit: int = 30,
                            filters: dict[str, Any] | None = None) -> list[dict]:
    """Поиск по банку кандидатов (ad-hoc потребность без сохранения в БД)."""
    fake = EmployerNeed(employer_id=uuid.uuid4(), title=query_text, description=query_text,
                        specialization_id=specialization_id, grade_id=grade_id, skills=[])
    fake.search_text = query_text
    fake.embedding = embed_text(query_text, query=True)
    f = dict(filters or {})
    if has_fsp is not None:
        f["has_fsp"] = has_fsp
    return await rank_candidates_for_need(db, fake, limit=limit, filters=f)


async def recommended_categories(db: AsyncSession, need: EmployerNeed) -> list[dict]:
    """«Рекомендованные категории» (ТЗ): категории с числом кандидатов и близостью к потребности."""
    counts = (await db.execute(
        select(CandidateProfile.category_id, func.count(CandidateProfile.id))
        .where(CandidateProfile.onboarding_completed == True, CandidateProfile.is_discoverable == True,  # noqa: E712
               CandidateProfile.category_id.is_not(None)).group_by(CandidateProfile.category_id))).all()
    cnt = {cid: n for cid, n in counts}
    if not cnt:
        return []
    cats = (await db.execute(select(Category).where(Category.id.in_(list(cnt))).options(
        selectinload(Category.specialization), selectinload(Category.grade)))).scalars().all()
    need_grade = await db.get(Grade, need.grade_id) if need.grade_id else None
    out = []
    for cat in cats:
        spec_ok = 1.0 if (not need.specialization_id or cat.specialization_id == need.specialization_id) else 0.0
        gfit = rk.grade_fit([need_grade.level] if need_grade else [], cat.grade.level if cat.grade else None)
        out.append({"category_id": cat.id, "slug": cat.slug, "label": cat.label, "candidates_count": cnt[cat.id],
                    "affinity": round(0.6 * spec_ok + 0.4 * gfit, 3)})
    out.sort(key=lambda r: (-r["affinity"], -r["candidates_count"]))
    return out


async def save_snapshot(db: AsyncSession, need: EmployerNeed, filters: dict, items: list[dict]) -> ShortlistSnapshot:
    snap = ShortlistSnapshot(need_id=need.id, filters=filters, results=items, algorithm_version=ALGORITHM_VERSION)
    db.add(snap)
    await db.flush()
    return snap
