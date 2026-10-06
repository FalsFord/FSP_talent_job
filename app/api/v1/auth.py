from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerProfile
from app.models.user import User, UserRole
from app.schemas.common import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if not body.consent_personal_data:
        raise HTTPException(status_code=400, detail="Consent required")
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    role = UserRole.candidate if body.role == "candidate" else UserRole.employer
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), role=role)
    db.add(user)
    await db.flush()
    if role == UserRole.candidate:
        db.add(CandidateProfile(user_id=user.id, privacy={"show_contacts_after_accept": True}))
    else:
        company = Company(name=f"Компания {body.email.split('@')[0]}")
        db.add(company)
        await db.flush()
        db.add(EmployerProfile(user_id=user.id, company_id=company.id))
    await db.commit()
    token = create_access_token(str(user.id), {"role": user.role.value})
    return TokenOut(access_token=token)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(str(user.id), {"role": user.role.value})
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
