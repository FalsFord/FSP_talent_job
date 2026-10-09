from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._common import candidate_profile
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.domain import grade_policy as gp
from app.models.assessment import AssessmentSession, SessionStatus
from app.models.user import User, UserRole
from app.schemas.assessment import (
    AnswerIn, AssessmentStatusOut, EventIn, ItemResultOut, OnboardingStartIn, QuestionOut, SessionOut, StartIn,
    SubmitAnswersIn, SubmitResultOut,
)
from app.services import assessment_service as svc

router = APIRouter(prefix="/assessments", tags=["assessments"])
_candidate = require_roles(UserRole.candidate)


def _session_out(s: AssessmentSession) -> SessionOut:
    return SessionOut(id=s.id, status=s.status.value, question_ids=s.question_ids, purpose=s.purpose,
                      deadline_at=s.deadline_at, time_limit_s=s.time_limit_s, languages=s.languages or [])


async def _own_session(db: AsyncSession, user: User, session_id: UUID):
    profile = await candidate_profile(db, user.id)
    s = await db.get(AssessmentSession, session_id)
    if not s or s.candidate_id != profile.id:
        raise DomainError("NOT_FOUND", "Session not found", 404)
    return profile, s


def _normalize_answers(raw: dict[str, dict]) -> dict[str, dict]:
    """Совместимость с прежним форматом ответов: допускаем ключи value | answer | selected."""
    out = {}
    for k, v in (raw or {}).items():
        if isinstance(v, dict):
            for key in ("value", "answer", "selected"):
                if key in v:
                    out[k] = {"value": v[key]}
                    break
    return out


async def _start(db, user, *, specialization_id, grade_id, languages, purpose) -> SessionOut:
    profile = await candidate_profile(db, user.id)
    session = await svc.start_session(db, profile, specialization_id=specialization_id, target_grade_id=grade_id,
                                      languages=languages, purpose=purpose)
    await db.commit()
    return _session_out(session)


@router.post("/onboarding/start", response_model=SessionOut)
async def onboarding_start(body: OnboardingStartIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    """Совместимый старт: цель попытки (первичная категоризация / повышение / понижение / переподтверждение)
    определяется автоматически по текущему подтверждённому грейду."""
    return await _start(db, user, specialization_id=body.specialization_id, grade_id=body.declared_grade_id,
                        languages=body.languages, purpose=None)


@router.post("/start", response_model=SessionOut)
async def start(body: StartIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    return await _start(db, user, specialization_id=body.specialization_id, grade_id=body.declared_grade_id,
                        languages=body.languages, purpose=body.purpose)


@router.get("/status", response_model=AssessmentStatusOut)
async def status(user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    return await svc.get_status(db, await candidate_profile(db, user.id))


@router.get("/sessions/{session_id}/questions", response_model=list[QuestionOut])
async def session_questions(session_id: UUID, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    _, s = await _own_session(db, user, session_id)
    return [QuestionOut(**svc.public_view(i)) for i in await svc.get_instances(db, s)]


@router.put("/sessions/{session_id}/answers/{instance_id}", status_code=204)
async def autosave(session_id: UUID, instance_id: UUID, body: AnswerIn, user: User = Depends(_candidate),
                   db: AsyncSession = Depends(get_db)):
    _, s = await _own_session(db, user, session_id)
    await svc.save_answer(db, s, instance_id, body.value)
    await db.commit()


@router.post("/sessions/{session_id}/events", status_code=204)
async def events(session_id: UUID, body: EventIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    _, s = await _own_session(db, user, session_id)
    await svc.record_event(db, s, body.type, body.meta)
    await db.commit()


def _result_out(profile, session, insts, per_lang, flags, category_label) -> SubmitResultOut:
    dec = session.decision or {}
    return SubmitResultOut(
        session_id=session.id, score=session.score or 0.0, passed=bool(session.passed),
        outcome_grade_id=session.outcome_grade_id, category_label=category_label, profile_strength=profile.profile_strength,
        result=session.result, scaled_score=session.scaled_score, confidence=session.confidence,
        decision_code=dec.get("code"), next_step=dec.get("next_step"),
        lower_grade_id=UUID(dec["lower_grade_id"]) if dec.get("lower_grade_id") else None,
        per_language=per_lang, integrity_flags=flags,
        items=[ItemResultOut(id=i.id, kind=i.kind, language=i.language, topic=i.topic, score=i.score,
                             details={k: v for k, v in (i.details or {}).items() if k in ("passed", "total", "error", "needs_review")})
               for i in insts])


@router.post("/sessions/{session_id}/submit", response_model=SubmitResultOut)
async def session_submit(session_id: UUID, body: SubmitAnswersIn, user: User = Depends(_candidate),
                         db: AsyncSession = Depends(get_db)):
    profile, s = await _own_session(db, user, session_id)
    out = await svc.submit_session(db, s, _normalize_answers(body.answers))
    await db.commit()
    if out.get("expired"):
        raise DomainError("SESSION_EXPIRED", "Время попытки истекло: результат не засчитан", 409)
    await db.refresh(profile, ["category"])
    return _result_out(profile, s, out["instances"], {k: round(v, 3) for k, v in out["lang_ratio"].items()}, out["flags"],
                       profile.category.label if profile.category else None)


@router.get("/sessions/{session_id}/result", response_model=SubmitResultOut)
async def session_result(session_id: UUID, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    profile, s = await _own_session(db, user, session_id)
    if s.status != SessionStatus.submitted:
        raise DomainError("RESULT_NOT_READY", "Результата ещё нет", 409)
    insts = await svc.get_instances(db, s)
    per: dict[str, list] = {}
    for i in insts:
        if i.score is not None:
            per.setdefault(i.language, []).append((i.score, i.weight))
    per_lang = {l: round(gp.session_ratio(v)[0], 3) for l, v in per.items()}
    await db.refresh(profile, ["category"])
    return _result_out(profile, s, insts, per_lang, s.integrity or [], profile.category.label if profile.category else None)


@router.get("/history")
async def history(user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    profile = await candidate_profile(db, user.id)
    rows = (await db.execute(select(AssessmentSession).where(AssessmentSession.candidate_id == profile.id)
                             .order_by(AssessmentSession.started_at.desc()).limit(50))).scalars().all()
    return [{"id": s.id, "purpose": s.purpose, "status": s.status.value, "result": s.result, "scaled_score": s.scaled_score,
             "started_at": s.started_at, "submitted_at": s.submitted_at, "languages": s.languages} for s in rows]
