"""Регулярные задания работодателей (доп. функционал ТЗ)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timezone
from app.services import git_eval_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import candidate_profile, employer_profile
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed, EmployerProfile
from app.models.platform import EmployerTask, TaskAssignment
from app.models.endpoint import EndpointState
from app.models.reference import Grade
from app.models.user import User, UserRole
from app.services import employer_task_service as svc
from app.services.task_attempts import assignment_version,evaluation_status
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
    answer: str | None = Field(default=None, min_length=20, max_length=8000)
    repo_url: str | None = Field(default=None, max_length=300)
    ref: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def solution(self):
        if bool(self.answer)==bool(self.repo_url):
            raise ValueError('Отправьте текст решения или ссылку на репозиторий')
        return self


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
    from app.services.task_readiness import require_ready
    meta=await task_metadata(db,t)
    require_ready([{**meta,'title':t.title,'statement':t.statement,'rubric':t.rubric}])
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
             "submitted_at": a.submitted_at, "eval_details":a.eval_details} for a, c in rows]


@router.patch("/employers/tasks/assignments/{assignment_id}")
async def review(assignment_id: UUID, body: ReviewIn, user: User = Depends(_employer), db: AsyncSession = Depends(get_db)):
    ep = await employer_profile(db, user.id)
    a = await db.get(TaskAssignment, assignment_id)
    t = await db.get(EmployerTask, a.task_id) if a else None
    if not a or not t or t.employer_id != ep.id:
        raise DomainError("NOT_FOUND", "Assignment not found", 404)
    if a.status not in ('submitted','reviewed'):
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
    output=[]
    for a,t,name in rows:
        meta=await assignment_version(db,a,t)
        if a.status=='assigned' and meta.get('offer_id'):
            attempt=await db.get(EndpointState,(user.id,'assessment:offer:'+meta['offer_id']))
            ep=await db.get(EmployerProfile,t.employer_id)
            sent=await db.get(EndpointState,(ep.user_id,'assessment-invitation:'+meta['offer_id']))
            index=next((i for i,item in enumerate(sent.data.get('tasks',[])) if item.get('task_id')==str(t.id)),None) if sent else None
            if attempt and attempt.data.get('done') and index is not None and not str(attempt.data.get('answers',{}).get(str(index), '')).strip():
                a.status='skipped'
        last=await db.get(EndpointState,(user.id,'practice:assignment:'+str(a.id)))
        clock=await db.get(EndpointState,(user.id,'assignment:clock:'+str(a.id)))
        output.append({"id": a.id, "title": meta['title'], "statement": meta['condition'], "company_name": name, "status": a.status,'evaluation_status':evaluation_status(a),'vacancy_id':meta.get('vacancy_id'),'vacancy_title':meta.get('vacancy_title'), 'check':last.data if last else None,'clock':clock.data if clock else None,
             "score": a.reviewer_score if a.reviewer_score is not None else a.auto_score, "assigned_at": a.assigned_at,
             "practice_id":meta.get('practice_id'),'sample':meta.get('sample'),'purpose':meta.get('purpose'), 'eval_details':a.eval_details})
    await db.commit()
    return output

async def assignment_clock(db,user_id,a,meta):
    from app.api.endpoint import state,save
    key='assignment:clock:'+str(a.id)
    clock=await state(db,user_id,key)
    now=int(datetime.now(timezone.utc).timestamp()*1000)
    if not clock:
        duration=max(1,int(meta.get('time') or 20))*60
        clock={'startedAt':now,'deadlineAt':now+duration*1000,'duration':duration}
        await save(db,user_id,key,clock);await db.commit()
    if now>=clock['deadlineAt']:
        a.status='expired';a.auto_score=0
        from app.services.notification_service import notify
        task=await db.get(EmployerTask,a.task_id)
        ep=await db.get(EmployerProfile,task.employer_id)
        await notify(db,ep.user_id,'assessment_failed','Соискатель не справился с тестовым',task.title+': время истекло.',{'url':'/employer/tasks'})
        await notify(db,user_id,'assessment_expired','Время тестового истекло',task.title+': задание не пройдено.',{'url':'/candidate/tasks'})
        await db.commit()
        raise DomainError('EXPIRED','Время выполнения истекло. Задание не пройдено.',409)
    return clock

@router.post('/candidates/me/tasks/{assignment_id}/start')
async def start_task(assignment_id:UUID,user:User=Depends(_candidate),db:AsyncSession=Depends(get_db)):
    c=await candidate_profile(db,user.id)
    a=await db.scalar(select(TaskAssignment).where(TaskAssignment.id==assignment_id).with_for_update())
    if not a or a.candidate_id!=c.id:raise DomainError('NOT_FOUND','Задание не найдено',404)
    if a.status!='assigned':raise DomainError('ALREADY_SUBMITTED','Задание завершено',409)
    return await assignment_clock(db,user.id,a,await assignment_version(db,a,await db.get(EmployerTask,a.task_id)))

async def task_metadata(db,t):
    ep=await db.get(EmployerProfile,t.employer_id)
    rows=(await db.execute(select(EndpointState.data).where(EndpointState.user_id==ep.user_id,EndpointState.key.like('taskset:%')))).scalars().all()
    return next((item for data in rows for item in data.get('tasks',[]) if item.get('task_id')==str(t.id)),{})


@router.post("/candidates/me/tasks/{assignment_id}/submit")
async def submit_task(assignment_id: UUID, body: SubmitIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    a = await db.scalar(select(TaskAssignment).where(TaskAssignment.id==assignment_id).with_for_update())
    if not a or a.candidate_id != c.id:
        raise DomainError("NOT_FOUND", "Assignment not found", 404)
    if a.status != "assigned":
        raise DomainError("ALREADY_SUBMITTED", "Решение уже отправлено", 409)
    t = await db.get(EmployerTask, a.task_id)
    meta=await assignment_version(db,a,t)
    await assignment_clock(db,user.id,a,meta)
    if body.repo_url:
        if meta.get('practice_id'):
            raise DomainError('CODE_REQUIRED','Алгоритмическое задание нужно проверить в редакторе',422)
        from app.services.github_url import normalize_repository
        body.repo_url,link_ref=normalize_repository(body.repo_url)
        if not body.ref:body.ref=link_ref
        a.answer,a.status,a.submitted_at=body.repo_url,'evaluating',datetime.now(timezone.utc)
        a.eval_details={'repo_url':body.repo_url,'ref':body.ref}
        await db.commit()
        state,detail=await git_eval_client.submit_evaluation(assignment_id=a.id,repo_url=body.repo_url,ref=body.ref,rubric=meta['rubric'],language=meta['language'])
        # A fast callback can finish before the queue request returns.
        await db.refresh(a)
        if a.status=='evaluating' and state!='queued':
            a.status='assigned' if state=='rejected' else 'submitted'
            a.eval_details={'error':{'code':state,'message':detail}}
            await db.commit()
        if state=='rejected': raise DomainError('BAD_REPO_URL',detail or 'Некорректный репозиторий',422)
        return {'id':a.id,'status':a.status,'auto_score':a.auto_score}
    execution=None
    if not meta.get('practice_id') and meta.get('purpose') in ('hiring','qualification'):
        raise DomainError('REPO_REQUIRED','Для этого задания прикрепите ссылку на GitHub-репозиторий',422)
    if meta.get('practice_id'):
        execution=await db.get(EndpointState,(user.id,'practice:assignment:'+str(a.id)))
        if not execution or execution.data.get('source_code')!=body.answer:
            raise DomainError('RUN_REQUIRED','Проверьте текущее решение в редакторе перед отправкой',422)
        result=execution.data.get('result',{})
        if not result.get('total') or result.get('passed')!=result['total']:
            raise DomainError('TESTS_REQUIRED','Для отправки алгоритма пройдите все проверочные тесты',422)
    if execution:
        a.answer,a.status,a.submitted_at=body.answer,'submitted',datetime.now(timezone.utc)
        result=execution.data['result']
        a.eval_details={'execution':result}
        a.auto_score=result['passed']/result['total']
        await svc._update_task_ratio(db,c,a.auto_score)
    else:
        from types import SimpleNamespace
        await svc.submit(db, a, SimpleNamespace(title=meta['title'],rubric=meta['rubric']), c, body.answer)
    await db.commit()
    return {"id": a.id, "status": a.status, "auto_score": a.auto_score}
