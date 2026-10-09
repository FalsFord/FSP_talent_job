"""Вакансии и отклики — дополнительный сценарий (ТЗ: «желательно, но не обязательно для MVP»)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import candidate_profile, employer_profile
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.domain.invitation_fsm import validate_salary
from app.domain.trust_rules import vacancy_trust
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerProfile, WorkFormat
from app.models.platform import ContactReveal
from app.models.user import User, UserRole
from app.models.vacancy import Application, ApplicationStatus, Vacancy
from app.services.matching_service import contacts_for, display_name
from app.services.notification_service import notify

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


class VacancyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    description: str = Field(min_length=10)
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    skills: list[str] = Field(default_factory=list)
    work_format: str | None = Field(default=None, pattern="^(remote|office|hybrid)$")
    salary_min: int = Field(ge=0)
    salary_max: int = Field(ge=0)


class ApplyIn(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=4000)


class ApplicationStatusIn(BaseModel):
    status: str = Field(pattern="^(viewed|accepted|rejected)$")


_APP_NEXT = {"submitted": {"viewed", "accepted", "rejected"}, "viewed": {"accepted", "rejected"}}


def _salary_check(lo: int, hi: int) -> None:
    err = validate_salary(lo, hi)
    if err:
        raise DomainError(err, "Зарплата «от–до» в рублях обязательна: «от» > 0, «до» не меньше «от»", 422)


def _vac_out(v: Vacancy, company: str | None = None) -> dict:
    return {"id": v.id, "title": v.title, "description": v.description, "salary_min": v.salary_min,
            "salary_max": v.salary_max, "skills": v.skills, "trust_score": v.trust_score, "trust_flags": v.trust_flags or [],
            "company_name": company, "is_active": v.is_active,
            "work_format": v.work_format.value if v.work_format else None, "created_at": v.created_at}


@router.get("")
async def list_vacancies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Vacancy, Company.name).join(EmployerProfile, EmployerProfile.id == Vacancy.employer_id)
                             .join(Company, Company.id == EmployerProfile.company_id).where(Vacancy.is_active == True)  # noqa: E712
                             .order_by(Vacancy.created_at.desc()))).all()
    return [_vac_out(v, name) for v, name in rows]


@router.get("/mine")
async def my_vacancies(user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    rows = (await db.execute(select(Vacancy).where(Vacancy.employer_id == ep.id).order_by(Vacancy.created_at.desc()))).scalars().all()
    return [_vac_out(v, ep.company.name) for v in rows]


@router.get("/applications/mine")
async def my_applications(user: User = Depends(require_roles(UserRole.candidate)), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    rows = (await db.execute(select(Application, Vacancy).join(Vacancy, Vacancy.id == Application.vacancy_id)
                             .where(Application.candidate_id == c.id).order_by(Application.created_at.desc()))).all()
    return [{"id": a.id, "vacancy_id": v.id, "vacancy_title": v.title, "status": a.status.value, "created_at": a.created_at}
            for a, v in rows]


@router.post("", status_code=201)
async def create_vacancy(body: VacancyCreate, user: User = Depends(require_roles(UserRole.employer)),
                         db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    _salary_check(body.salary_min, body.salary_max)       # ТЗ п.2.2(1): зарплата обязательна и в вакансии
    age = (datetime.now(timezone.utc) - user.created_at).days if user.created_at else 365
    score, flags = vacancy_trust(salary_from=body.salary_min, salary_to=body.salary_max, text=f"{body.title}\n{body.description}",
                                 account_age_days=age)
    v = Vacancy(employer_id=ep.id, title=body.title, description=body.description, specialization_id=body.specialization_id,
                grade_id=body.grade_id, skills=body.skills, work_format=WorkFormat(body.work_format) if body.work_format else None,
                salary_min=body.salary_min, salary_max=body.salary_max, trust_score=score, trust_flags=flags)
    db.add(v)
    await db.commit()
    return {"id": v.id, "trust_score": score, "trust_flags": flags}


async def _own_vacancy(db: AsyncSession, ep: EmployerProfile, vid: UUID) -> Vacancy:
    v = await db.get(Vacancy, vid)
    if not v or v.employer_id != ep.id:
        raise DomainError("NOT_FOUND", "Vacancy not found", 404)
    return v


@router.put("/{vacancy_id}")
async def update_vacancy(vacancy_id: UUID, body: VacancyCreate, user: User = Depends(require_roles(UserRole.employer)),
                         db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    v = await _own_vacancy(db, ep, vacancy_id)
    _salary_check(body.salary_min, body.salary_max)
    for f in ("title", "description", "specialization_id", "grade_id", "skills", "salary_min", "salary_max"):
        setattr(v, f, getattr(body, f))
    v.work_format = WorkFormat(body.work_format) if body.work_format else None
    age = (datetime.now(timezone.utc) - user.created_at).days if user.created_at else 365
    v.trust_score, v.trust_flags = vacancy_trust(salary_from=v.salary_min, salary_to=v.salary_max,
                                                 text=f"{v.title}\n{v.description}", account_age_days=age)
    await db.commit()
    return _vac_out(v, ep.company.name)


@router.post("/{vacancy_id}/close")
async def close_vacancy(vacancy_id: UUID, user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    v = await _own_vacancy(db, ep, vacancy_id)
    v.is_active = False
    await db.commit()
    return {"id": v.id, "is_active": False}


@router.post("/{vacancy_id}/apply", status_code=201)
async def apply_vacancy(vacancy_id: UUID, body: ApplyIn | None = None, user: User = Depends(require_roles(UserRole.candidate)),
                        db: AsyncSession = Depends(get_db)):
    """Отклик кандидата. По ТЗ контакты кандидата раскрываются работодателю, когда кандидат «откликнулся сам»."""
    profile = await candidate_profile(db, user.id)
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy or not vacancy.is_active:
        raise DomainError("NOT_FOUND", "Vacancy not found", 404)
    dup = (await db.execute(select(Application.id).where(Application.vacancy_id == vacancy_id,
                                                         Application.candidate_id == profile.id))).first()
    if dup:
        raise DomainError("ALREADY_APPLIED", "Вы уже откликались на эту вакансию", 409)
    app = Application(vacancy_id=vacancy_id, candidate_id=profile.id, status=ApplicationStatus.submitted,
                      cover_letter=body.cover_letter if body else None)
    db.add(app)
    await db.flush()
    revealed = (await db.execute(select(ContactReveal.id).where(ContactReveal.candidate_id == profile.id,
                                                                ContactReveal.employer_id == vacancy.employer_id))).first()
    if not revealed:
        db.add(ContactReveal(candidate_id=profile.id, employer_id=vacancy.employer_id, source="application", source_id=app.id))
    ep = await db.get(EmployerProfile, vacancy.employer_id)
    if ep:
        await notify(db, ep.user_id, "application_received", "Новый отклик", vacancy.title, {"application_id": str(app.id)})
    await db.commit()
    return {"id": app.id, "status": app.status.value}


@router.get("/{vacancy_id}/applications")
async def vacancy_applications(vacancy_id: UUID, user: User = Depends(require_roles(UserRole.employer)),
                               db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    v = await _own_vacancy(db, ep, vacancy_id)
    rows = (await db.execute(select(Application, CandidateProfile).join(CandidateProfile, CandidateProfile.id == Application.candidate_id)
                             .where(Application.vacancy_id == v.id).order_by(Application.created_at.desc()))).all()
    out = []
    for a, c in rows:
        out.append({"id": a.id, "candidate_id": c.id, "display_name": display_name(c, True), "status": a.status.value,
                    "cover_letter": a.cover_letter, "profile_strength": c.profile_strength, "created_at": a.created_at,
                    "contacts": await contacts_for(db, ep.id, c)})
    return out


@router.patch("/applications/{application_id}")
async def update_application(application_id: UUID, body: ApplicationStatusIn,
                             user: User = Depends(require_roles(UserRole.employer)), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    a = await db.get(Application, application_id)
    v = await db.get(Vacancy, a.vacancy_id) if a else None
    if not a or not v or v.employer_id != ep.id:
        raise DomainError("NOT_FOUND", "Application not found", 404)
    if a.status.value == body.status:
        return {"id": a.id, "status": a.status.value}
    if body.status not in _APP_NEXT.get(a.status.value, set()):
        raise DomainError("INVALID_TRANSITION", f"Переход «{a.status.value}» → «{body.status}» недопустим", 409)
    a.status, a.updated_at = ApplicationStatus(body.status), datetime.now(timezone.utc)
    c = await db.get(CandidateProfile, a.candidate_id)
    if c:
        await notify(db, c.user_id, "application_status", "Статус отклика изменён", f"{v.title}: {body.status}",
                     {"application_id": str(a.id), "status": body.status})
    await db.commit()
    return {"id": a.id, "status": a.status.value}
