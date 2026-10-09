from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import DomainError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerProfile
from app.models.user import User, UserRole
from app.schemas.common import LoginIn, MessageOut, RegisterIn, TokenOut, UserOut
from app.services.auth_service import issue_verification, verify_token

router = APIRouter(prefix="/auth", tags=["auth"])


class VerifyIn(BaseModel):
    token: str


class ResendIn(BaseModel):
    email: EmailStr


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if not body.consent_personal_data:
        raise HTTPException(status_code=400, detail="Consent required")
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    role = UserRole.candidate if body.role == "candidate" else UserRole.employer
    need_verify = settings.require_email_verification
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), role=role,
                email_verified=not need_verify)
    db.add(user)
    await db.flush()
    if role == UserRole.candidate:
        db.add(CandidateProfile(user_id=user.id, privacy={"show_contacts_after_accept": True}))
    else:
        company = Company(name=f"Компания {body.email.split('@')[0]}")
        db.add(company)
        await db.flush()
        db.add(EmployerProfile(user_id=user.id, company_id=company.id))
    raw = await issue_verification(db, user) if need_verify else None
    await db.commit()
    if need_verify:     # ТЗ п.2.2(4): регистрация по e-mail с подтверждением адреса — токен выдаётся после подтверждения
        return TokenOut(access_token="", verification_required=True, dev_verification_token=raw if settings.debug else None)
    return TokenOut(access_token=create_access_token(str(user.id), {"role": user.role.value}))


@router.post("/verify-email", response_model=MessageOut)
async def verify_email(body: VerifyIn, db: AsyncSession = Depends(get_db)):
    await verify_token(db, body.token)
    await db.commit()
    return MessageOut(detail="Email подтверждён")


@router.post("/resend-verification", response_model=MessageOut, status_code=202)
async def resend_verification(body: ResendIn, db: AsyncSession = Depends(get_db)):
    """Ответ одинаков независимо от существования адреса (не раскрываем зарегистрированные e-mail)."""
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user and not user.email_verified:
        await issue_verification(db, user)
        await db.commit()
    return MessageOut(detail="Если адрес зарегистрирован и не подтверждён, письмо отправлено")


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if settings.require_email_verification and not user.email_verified:
        raise DomainError("EMAIL_NOT_VERIFIED", "Подтвердите адрес электронной почты", 403)
    return TokenOut(access_token=create_access_token(str(user.id), {"role": user.role.value}))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
