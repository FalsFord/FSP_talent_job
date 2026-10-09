from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingStartIn(BaseModel):
    specialization_id: UUID
    declared_grade_id: UUID
    languages: list[str] | None = Field(default=None, description="python | java | sql; по умолчанию — по специализации")


class StartIn(BaseModel):
    """Общий старт попытки. purpose определяется автоматически (onboarding/up/down/reattest); micro — явно."""

    specialization_id: UUID | None = None
    declared_grade_id: UUID | None = None
    languages: list[str] | None = None
    purpose: str | None = Field(default=None, pattern="^(micro)$")


class QuestionOut(BaseModel):
    id: UUID
    prompt: str
    question_type: str
    options: dict | None
    kind: str | None = None
    language: str | None = None
    topic: str | None = None
    time_limit_s: int | None = None
    public: dict[str, Any] = Field(default_factory=dict)
    answer: Any | None = None


class SessionOut(BaseModel):
    id: UUID
    status: str
    question_ids: list[str]
    purpose: str | None = None
    deadline_at: datetime | None = None
    time_limit_s: int | None = None
    languages: list[str] = Field(default_factory=list)


class SubmitAnswersIn(BaseModel):
    answers: dict[str, dict] = Field(default_factory=dict)


class AnswerIn(BaseModel):
    value: Any


class EventIn(BaseModel):
    type: str = Field(max_length=32, pattern="^(blur|focus|paste|copy|visibility)$")
    meta: dict[str, Any] = Field(default_factory=dict)


class ItemResultOut(BaseModel):
    id: UUID
    kind: str
    language: str
    topic: str
    score: float | None
    details: dict[str, Any] = Field(default_factory=dict)


class SubmitResultOut(BaseModel):
    session_id: UUID
    score: float
    passed: bool
    outcome_grade_id: UUID | None
    category_label: str | None
    profile_strength: float
    result: str | None = None                     # pass | borderline | fail
    scaled_score: float | None = None
    confidence: float | None = None
    decision_code: str | None = None
    next_step: str | None = None                  # continue | try_lower | retry_later | can_try_higher
    lower_grade_id: UUID | None = None
    per_language: dict[str, float] = Field(default_factory=dict)
    integrity_flags: list[str] = Field(default_factory=list)
    items: list[ItemResultOut] = Field(default_factory=list)


class AssessmentStatusOut(BaseModel):
    confirmed_grade_id: UUID | None
    verification_status: str
    valid_until: datetime | None
    grade_change_available: bool | None
    grade_change_available_at: datetime | None
    micro_test_due: bool
    micro_test_available_at: datetime | None
    languages: list[str]
    code_tasks_enabled: bool
