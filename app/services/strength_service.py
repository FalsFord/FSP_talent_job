"""Пересчёт «силы подтверждённого профиля» (ранжирование внутри категории, ТЗ п.2.1)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain import grade_policy as gp
from app.domain import ranking as rk
from app.models.candidate import CandidateProfile
from app.models.fsp import FSPParticipantLink


async def fsp_inputs(db: AsyncSession, candidate_id) -> list[dict]:
    res = await db.execute(select(FSPParticipantLink).where(FSPParticipantLink.candidate_id == candidate_id)
                           .options(selectinload(FSPParticipantLink.achievements)))
    link = res.scalar_one_or_none()
    if not link:
        return []          # нет истории ФСП — корректный случай (ТЗ), бонуса нет, штрафа нет
    return [{"place": a.rank, "date": a.event_date} for a in link.achievements]


async def recompute_strength(db: AsyncSession, c: CandidateProfile, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    fsp = rk.fsp_score(await fsp_inputs(db, c.id))
    freshness = gp.freshness_multiplier(now, c.grade_valid_until) if c.confirmed_grade_id else gp.STALE_FLOOR
    c.profile_strength = rk.strength_score(test_ratio=c.last_test_ratio, fsp=fsp, task_ratio=c.task_ratio,
                                           freshness=freshness)
    return c.profile_strength
