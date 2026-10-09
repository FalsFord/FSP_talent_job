from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvitationCreate(BaseModel):
    candidate_id: UUID
    vacancy_id: UUID | None = None
    title: str = Field(min_length=3, max_length=256)
    message: str = Field(min_length=5)
    salary_min: int = Field(ge=0, description="руб., обязательно (ТЗ п.2.2)")
    salary_max: int = Field(ge=0, description="руб., обязательно (ТЗ п.2.2)")
    contact_method: str | None = Field(default=None, max_length=256, description="способ связи; по умолчанию e-mail работодателя")


class InvitationStatusUpdate(BaseModel):
    status: str = Field(pattern="^(viewed|accepted|declined|withdrawn)$")


class InvitationEventOut(BaseModel):
    from_status: str | None
    to_status: str
    actor: str
    created_at: datetime


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    message: str
    salary_min: int
    salary_max: int
    currency: str = "RUB"
    status: str
    company_name: str | None = None
    company_contact: str | None = None
    candidate_display: str | None = None
    candidate_contacts: dict | None = None
    vacancy_id: UUID | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    viewed_at: datetime | None = None
    decided_at: datetime | None = None
