from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.employer import MatchedCandidateOut, MatchExplanation
from app.services.matching_service import search_candidates

router = APIRouter(prefix="/search", tags=["search"])


class CandidateSearchIn(BaseModel):
    query: str = Field(min_length=2)
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    has_fsp: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/candidates", response_model=list[MatchedCandidateOut])
async def search_candidates_endpoint(
    body: CandidateSearchIn,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    ranked = await search_candidates(
        db,
        body.query,
        body.specialization_id,
        body.grade_id,
        body.has_fsp,
        body.limit,
    )
    out = []
    for row in ranked:
        c = row["candidate"]
        out.append(
            MatchedCandidateOut(
                candidate_id=c.id,
                display_name=f"{c.first_name or ''} {c.last_name or ''}".strip() or "Кандидат",
                category_label=c.category.label if c.category else None,
                match_score=row["match_score"],
                explanation=MatchExplanation(**row["explanation"]),
                contacts_hidden=True,
            )
        )
    return out
