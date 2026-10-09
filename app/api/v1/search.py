from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import employer_profile, matched_out
from app.core.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.employer import MatchedCandidateOut, ShortlistFilters
from app.services.matching_service import revealed_candidate_ids, search_candidates

router = APIRouter(prefix="/search", tags=["search"])


class CandidateSearchIn(BaseModel):
    query: str = Field(min_length=2)
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    has_fsp: bool | None = None
    filters: ShortlistFilters = Field(default_factory=ShortlistFilters)
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/candidates", response_model=list[MatchedCandidateOut])
async def search_candidates_endpoint(body: CandidateSearchIn, user: User = Depends(require_roles(UserRole.employer)),
                                     db: AsyncSession = Depends(get_db)):
    """Поиск по банку кандидатов: фильтры по специализации, грейду, стеку, достижениям ФСП; ранжирование по
    соответствию запросу и силе подтверждённого профиля, с объяснением."""
    ep = await employer_profile(db, user.id)
    ranked = await search_candidates(db, body.query, body.specialization_id, body.grade_id, body.has_fsp, body.limit,
                                     filters=body.filters.model_dump(exclude_none=True))
    revealed = await revealed_candidate_ids(db, ep.id)
    return [matched_out(r, revealed) for r in ranked]
