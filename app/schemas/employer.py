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


class MatchedCandidateOut(BaseModel):
    candidate_id: UUID
    display_name: str
    category_label: str | None
    match_score: float
    explanation: MatchExplanation
    contacts_hidden: bool = True
