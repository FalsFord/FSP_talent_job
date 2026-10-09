"""Общие помощники API-слоя."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.schemas.employer import MatchedCandidateOut, MatchExplanation
from app.services.matching_service import display_name


async def employer_profile(db: AsyncSession, user_id: UUID) -> EmployerProfile:
    res = await db.execute(select(EmployerProfile).where(EmployerProfile.user_id == user_id)
                           .options(selectinload(EmployerProfile.company)))
    ep = res.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Employer profile not found")
    return ep


async def candidate_profile(db: AsyncSession, user_id: UUID) -> CandidateProfile:
    res = await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Profile not found")
    return c


def matched_out(row: dict, revealed: set) -> MatchedCandidateOut:
    c: CandidateProfile = row["candidate"]
    return MatchedCandidateOut(
        candidate_id=c.id, display_name=display_name(c, c.id in revealed),
        category_label=c.category.label if c.category else None, match_score=row["match_score"],
        explanation=MatchExplanation(**row["explanation"]), contacts_hidden=c.id not in revealed)
