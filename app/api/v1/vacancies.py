from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_roles
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile, WorkFormat
from app.models.user import User, UserRole
from app.models.vacancy import Application, ApplicationStatus, Vacancy

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


class VacancyCreate(BaseModel):
    title: str
    description: str
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    skills: list[str] = Field(default_factory=list)
    work_format: str | None = None
    salary_min: int = Field(ge=0)
    salary_max: int = Field(ge=0)


@router.get("")
async def list_vacancies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Vacancy).where(Vacancy.is_active == True).order_by(Vacancy.created_at.desc()))  # noqa: E712
    return [
        {
            "id": v.id,
            "title": v.title,
            "description": v.description,
            "salary_min": v.salary_min,
            "salary_max": v.salary_max,
            "skills": v.skills,
            "trust_score": v.trust_score,
        }
        for v in result.scalars().all()
    ]


@router.post("", status_code=201)
async def create_vacancy(
    body: VacancyCreate,
    user: User = Depends(require_roles(UserRole.employer)),
    db: AsyncSession = Depends(get_db),
):
    ep_result = await db.execute(select(EmployerProfile).where(EmployerProfile.user_id == user.id))
    ep = ep_result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Employer not found")
    wf = WorkFormat(body.work_format) if body.work_format else None
    v = Vacancy(
        employer_id=ep.id,
        title=body.title,
        description=body.description,
        specialization_id=body.specialization_id,
        grade_id=body.grade_id,
        skills=body.skills,
        work_format=wf,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
    )
    db.add(v)
    await db.commit()
    return {"id": v.id}


@router.post("/{vacancy_id}/apply")
async def apply_vacancy(
    vacancy_id: UUID,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy or not vacancy.is_active:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    app = Application(vacancy_id=vacancy_id, candidate_id=profile.id, status=ApplicationStatus.submitted)
    db.add(app)
    await db.commit()
    return {"id": app.id, "status": app.status.value}
