from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingStartIn(BaseModel):
    specialization_id: UUID
    declared_grade_id: UUID


class QuestionOut(BaseModel):
    id: UUID
    prompt: str
    question_type: str
    options: dict | None


class SessionOut(BaseModel):
    id: UUID
    status: str
    question_ids: list[str]


class SubmitAnswersIn(BaseModel):
    answers: dict[str, dict] = Field(default_factory=dict)


class SubmitResultOut(BaseModel):
    session_id: UUID
    score: float
    passed: bool
    outcome_grade_id: UUID | None
    category_label: str | None
    profile_strength: float
