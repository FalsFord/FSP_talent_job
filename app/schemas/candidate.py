from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    headline: str | None = None
    city: str | None = None
    remote_ok: bool | None = None
    phone: str | None = None
    about: str | None = None
    skills: list[str] | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    label: str


class CandidateProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str | None
    last_name: str | None
    headline: str | None
    city: str | None
    remote_ok: bool
    about: str | None
    profile_strength: float
    onboarding_completed: bool
    category: CategoryOut | None = None
    phone: str | None = None


class CandidatePublicOut(BaseModel):
    id: UUID
    display_name: str
    headline: str | None
    category_label: str | None
    profile_strength: float
    skills: list[str]
    fsp_achievements_count: int
    contacts_hidden: bool = True
    phone: str | None = None
    email: str | None = None
    verification_status: str | None = None
    grade_valid_until: datetime | None = None
    verified_skills: list[str] = Field(default_factory=list)
    fsp_achievements: list[dict] = Field(default_factory=list)   # пусто = истории ФСП нет (корректный случай)
    fsp_linked: bool = False


class FSPLinkIn(BaseModel):
    external_id: str | None = None


class PrivacyUpdate(BaseModel):
    show_contacts_after_accept: bool = True
    show_full_name: bool = False        # показывать полное имя до принятия приглашения (по умолчанию «Имя Ф.»)
    is_discoverable: bool = True        # виден ли профиль работодателям в банке и подборках
