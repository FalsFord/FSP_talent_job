from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    website: str | None = None
    industry: str | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    website: str | None
    industry: str | None
    trust_score: float


class NeedCreate(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    description: str = Field(min_length=10)
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    skills: list[str] = Field(default_factory=list)
    work_format: str | None = Field(default=None, pattern="^(remote|office|hybrid)$")
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)


class NeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    skills: list[str]
    work_format: str | None
    salary_min: int | None
    salary_max: int | None


class MatchExplanation(BaseModel):
    semantic: float
    keyword: float
    grade_match: bool
    skills_matched: list[str]
    skills_missing: list[str]
    profile_strength: float
    fsp_achievements_count: int
    rank_score: float | None = None
    match_component: float | None = None
    verification_status: str | None = None          # confirmed | stale | unconfirmed
    skills_verified: list[str] = Field(default_factory=list)
    reasons: list[dict] = Field(default_factory=list)   # [{code, text, weight}] — краткая объяснимость выдачи


class MatchedCandidateOut(BaseModel):
    candidate_id: UUID
    display_name: str
    category_label: str | None
    match_score: float
    explanation: MatchExplanation
    contacts_hidden: bool = True


class ShortlistFilters(BaseModel):
    city: str | None = None
    has_fsp: bool | None = None
    verified_only: bool | None = None
    skills_all: list[str] | None = None
    min_strength: float | None = Field(default=None, ge=0, le=100)
    grade_ids: list[UUID] | None = None


class ShortlistIn(BaseModel):
    filters: ShortlistFilters = Field(default_factory=ShortlistFilters)
    limit: int = Field(default=50, ge=1, le=100)


class CategoryRecommendation(BaseModel):
    category_id: UUID
    slug: str
    label: str
    candidates_count: int
    affinity: float


class ShortlistOut(BaseModel):
    snapshot_id: UUID
    filters: dict
    categories: list[CategoryRecommendation]
    candidates: list[MatchedCandidateOut]


class TaskPreviewIn(BaseModel):
    language: str | None = Field(default=None, pattern="^(python|java|sql)$")
    grade: str | None = Field(default=None, pattern="^(intern|junior|middle|senior|lead)$")
    seed: int | None = None
    n_items: int = Field(default=6, ge=3, le=12)
