from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MessageOut(BaseModel):
    detail: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(pattern="^(candidate|employer)$")
    consent_personal_data: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    email_verified: bool
