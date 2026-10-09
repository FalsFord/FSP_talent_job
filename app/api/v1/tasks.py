"""Регулярные задания работодателей (доп. функционал ТЗ)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import candidate_profile, employer_profile
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed, EmployerProfile
from app.models.platform import EmployerTask, TaskAssignment
from app.models.reference import Grade
from app.models.user import User, UserRole
from app.services import employer_task_service as svc
from app.services.matching_service import display_name, revealed_candidate_ids

router = APIRouter(tags=["tasks"])
_employer, _candidate = require_roles(UserRole.employer), require_roles(UserRole.candidate)


class DraftIn(BaseModel):
    need_id: UUID | None = None
    language: str = Field(pattern="^(python|java|sql)$")
    grade: str = Field(default="middle", pattern="^(middle|senior|lead)$")
    seed: int | None = None


class RubricPoint(BaseModel):
    point: str
    keywords: list[str]


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    statement: str = Field(min_length=20)
    specialization_id: UUID | None = None
    grade_id: UUID | None = None
    language: str | None = Field(default=None, pattern="^(python|java|sql)$")
    rubric: list[RubricPoint] = Field(default_factory=list)
    origin: str = Field(default="manual", pattern="^(manual|rag)$")
    sources: list[str] = Field(default_factory=list)


class AssignIn(BaseModel):
    candidate_ids: list[UUID] | None = None
    top_n: int = Field(default=10, ge=1, le=50)


class ReviewIn(BaseModel):
    score: float = Field(ge=0, le=1)


class SubmitIn(BaseModel):
    answer: str = Field(min_length=20, max_length=8000)


@router.post("/employers/tasks/draft")
async def draft(body: DraftIn, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    text = ""
    if body.need_id:
        need = await db.get(EmployerNeed, body.need_id)
        if not need or need.employer_id != ep.id:
            raise DomainError("NOT_FOUND", "Need not found", 404)
        text = f"{need.title} {need.description} {' '.join(need.skills or [])}"
    return await svc.draft_from_context(db, language=body.language, grade=body.grade, context_text=text, seed=body.seed)


@router.post("/employers/tasks", status_code=201)
async def create_task(body: TaskCreate, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    t = EmployerTask(employer_id=ep.id, title=body.title, statement=body.statement, specialization_id=body.specialization_id,
                     grade_id=body.grade_id, language=body.language, origin=body.origin, sources=body.sources,
                     rubric=svc.normalize_rubric([r.model_dump() for r in body.rubric]))
    db.add(t)
    await db.commit()
    return {"id": t.id, "rubric_points": len(t.rubric)}


@router.get("/employers/tasks")
async def list_tasks(user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    rows = (await db.execute(select(EmployerTask).where(EmployerTask.employer_id == ep.id)
                             .order_by(EmployerTask.created_at.desc()))).scalars().all()
    return [{"id": t.id, "title": t.title, "language": t.language, "origin": t.origin, "is_active": t.is_active,
             "created_at": t.created_at} for t in rows]


async def _own_task(db: AsyncSession, ep: EmployerProfile, task_id: UUID) -> EmployerTask:
    t = await db.get(EmployerTask, task_id)
    if not t or t.employer_id != ep.id:
        raise DomainError("NOT_FOUND", "Task not found", 404)
    return t


@router.post("/employers/tasks/{task_id}/assign")
async def assign(task_id: UUID, body: AssignIn, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    t = await _own_task(db, ep, task_id)
    n = await svc.assign(db, t, body.candidate_ids, body.top_n)
    await db.commit()
    return {"assigned": n}


@router.get("/employers/tasks/{task_id}/assignments")
async def assignments(task_id: UUID, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    t = await _own_task(db, ep, task_id)
    rows = (await db.execute(select(TaskAssignment, CandidateProfile).join(CandidateProfile, CandidateProfile.id == TaskAssignment.candidate_id)
                             .where(TaskAssignment.task_id == t.id).order_by(TaskAssignment.assigned_at.desc()))).all()
    revealed = await revealed_candidate_ids(db, ep.id)
    return [{"id": a.id, "candidate_id": c.id, "display_name": display_name(c, c.id in revealed), "status": a.status,
             "answer": a.answer, "auto_score": a.auto_score, "reviewer_score": a.reviewer_score,
             "submitted_at": a.submitted_at} for a, c in rows]


@router.patch("/employers/tasks/assignments/{assignment_id}")
async def review(assignment_id: UUID, body: ReviewIn, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    a = await db.get(TaskAssignment, assignment_id)
    t = await db.get(EmployerTask, a.task_id) if a else None
    if not a or not t or t.employer_id != ep.id:
        raise DomainError("NOT_FOUND", "Assignment not found", 404)
    if a.status == "assigned":
        raise DomainError("NOT_SUBMITTED", "Кандидат ещё не прислал решение", 409)
    c = await db.get(CandidateProfile, a.candidate_id)
    await svc.review(db, a, c, body.score, t.title)
    await db.commit()
    return {"id": a.id, "status": a.status, "reviewer_score": a.reviewer_score}


@router.get("/candidates/me/tasks")
async def my_tasks(user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    rows = (await db.execute(select(TaskAssignment, EmployerTask, Company.name)
                             .join(EmployerTask, EmployerTask.id == TaskAssignment.task_id)
                             .join(EmployerProfile, EmployerProfile.id == EmployerTask.employer_id)
                             .join(Company, Company.id == EmployerProfile.company_id)
                             .where(TaskAssignment.candidate_id == c.id).order_by(TaskAssignment.assigned_at.desc()))).all()
    return [{"id": a.id, "title": t.title, "statement": t.statement, "company_name": name, "status": a.status,
             "score": a.reviewer_score if a.reviewer_score is not None else a.auto_score, "assigned_at": a.assigned_at}
            for a, t, name in rows]


@router.post("/candidates/me/tasks/{assignment_id}/submit")
async def submit_task(assignment_id: UUID, body: SubmitIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    a = await db.get(TaskAssignment, assignment_id)
    if not a or a.candidate_id != c.id:
        raise DomainError("NOT_FOUND", "Assignment not found", 404)
    if a.status != "assigned":
        raise DomainError("ALREADY_SUBMITTED", "Решение уже отправлено", 409)
    t = await db.get(EmployerTask, a.task_id)
    await svc.submit(db, a, t, c, body.answer)
    await db.commit()
    return {"id": a.id, "status": a.status, "auto_score": a.auto_score}
