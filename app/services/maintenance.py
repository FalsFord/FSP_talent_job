"""Фоновое обслуживание без внешнего планировщика: истечение приглашений и просроченных попыток,
ежесуточный пересчёт силы профиля (учёт «устаревания» подтверждения грейда)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assessment import AssessmentSession, SessionStatus
from app.models.candidate import CandidateProfile
from app.services import invitation_service
from app.services.strength_service import recompute_strength

log = logging.getLogger("maintenance")


async def expire_sessions(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    from app.services.assessment_service import _is_overdue

    rows = (await db.execute(select(AssessmentSession).where(AssessmentSession.status == SessionStatus.in_progress))).scalars().all()
    n = 0
    for s in rows:
        if _is_overdue(s, now):
            s.status, s.result, s.decision = SessionStatus.expired, "fail", {"code": "EXPIRED", "next_step": "retry_later"}
            n += 1
    return n


async def recompute_all_strengths(db: AsyncSession, batch: int = 200) -> int:
    ids = (await db.execute(select(CandidateProfile.id).where(CandidateProfile.confirmed_grade_id.is_not(None)))).scalars().all()
    for i in range(0, len(ids), batch):
        for c in (await db.execute(select(CandidateProfile).where(CandidateProfile.id.in_(ids[i:i + batch])))).scalars().all():
            await recompute_strength(db, c)
        await db.commit()
    return len(ids)


async def run_cycle(db: AsyncSession, *, daily: bool) -> dict:
    from app.models.endpoint import EndpointState
    from app.models.invitation import Invitation
    from app.api.endpoint import expire_company_assessment
    from uuid import UUID
    attempts=(await db.execute(select(EndpointState).where(EndpointState.key.like('assessment:offer:%')))).scalars().all()
    for attempt in attempts:
        if attempt.data.get('done'): continue
        inv=await db.get(Invitation,UUID(attempt.key.split(':')[-1]))
        if inv: await expire_company_assessment(db,inv,attempt.user_id)
    from app.models.platform import TaskAssignment,EmployerTask
    from app.api.v1.tasks import assignment_clock,task_metadata
    from app.core.errors import DomainError
    clocks=(await db.execute(select(EndpointState).where(EndpointState.key.like('assignment:clock:%')))).scalars().all()
    for clock in clocks:
        if clock.data.get('deadlineAt',float('inf'))>datetime.now(timezone.utc).timestamp()*1000: continue
        assignment=await db.get(TaskAssignment,UUID(clock.key.split(':')[-1]))
        if not assignment or assignment.status!='assigned': continue
        try: await assignment_clock(db,clock.user_id,assignment,await task_metadata(db,await db.get(EmployerTask,assignment.task_id)))
        except DomainError as exc:
            if exc.code!='EXPIRED': raise
    out = {"invitations_expired": await invitation_service.expire_stale(db), "sessions_expired": await expire_sessions(db)}
    await db.commit()
    if daily:
        out["strength_recomputed"] = await recompute_all_strengths(db)
    from app.services.ats_service import retry_pending
    await retry_pending(db)
    return out
