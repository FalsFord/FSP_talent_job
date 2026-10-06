from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvitationCreate(BaseModel):
    candidate_id: UUID
    vacancy_id: UUID | None = None
    title: str = Field(min_length=3, max_length=256)
    message: str = Field(min_length=5)
    salary_min: int = Field(ge=0)
    salary_max: int = Field(ge=0)


class InvitationStatusUpdate(BaseModel):
    status: str = Field(pattern="^(viewed|accepted|declined)$")


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    message: str
    salary_min: int
    salary_max: int
    status: str
    company_name: str | None = None
    candidate_display: str | None = None
    candidate_contacts: dict | None = None
