from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_roles
from app.models.assessment import AssessmentQuestion, AssessmentSession, SessionStatus
from app.models.user import User, UserRole
from app.schemas.assessment import OnboardingStartIn, QuestionOut, SessionOut, SubmitAnswersIn, SubmitResultOut
from app.models.assessment import SessionType
from app.services.assessment_service import start_onboarding_session, submit_session
from app.services.profile_service import get_candidate_by_user

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("/onboarding/start", response_model=SessionOut)
async def onboarding_start(
    body: OnboardingStartIn,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        session = await start_onboarding_session(
            db, profile, body.specialization_id, body.declared_grade_id, SessionType.onboarding
        )
        await db.commit()
    except ValueError as e:
        code = str(e)
        if code == "ACTIVE_SESSION":
            raise HTTPException(status_code=409, detail="Active session exists")
        raise HTTPException(status_code=503, detail="No questions in bank")
    return SessionOut(id=session.id, status=session.status.value, question_ids=session.question_ids)


@router.get("/sessions/{session_id}/questions", response_model=list[QuestionOut])
async def session_questions(
    session_id: UUID,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    session = await db.get(AssessmentSession, session_id)
    if not session or session.candidate_id != profile.id:
        raise HTTPException(status_code=404, detail="Session not found")
    out = []
    for qid in session.question_ids:
        q = await db.get(AssessmentQuestion, UUID(qid))
        if q:
            out.append(
                QuestionOut(
                    id=q.id,
                    prompt=q.prompt,
                    question_type=q.question_type.value,
                    options=q.options,
                )
            )
    return out


@router.post("/sessions/{session_id}/submit", response_model=SubmitResultOut)
async def session_submit(
    session_id: UUID,
    body: SubmitAnswersIn,
    user: User = Depends(require_roles(UserRole.candidate)),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_candidate_by_user(db, user.id)
    session = await db.get(AssessmentSession, session_id)
    if not session or session.candidate_id != profile.id:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        session = await submit_session(db, session, body.answers)
        await db.commit()
        await db.refresh(profile, ["category"])
    except ValueError:
        raise HTTPException(status_code=409, detail="Session not active")
    return SubmitResultOut(
        session_id=session.id,
        score=session.score or 0,
        passed=bool(session.passed),
        outcome_grade_id=session.outcome_grade_id,
        category_label=profile.category.label if profile.category else None,
        profile_strength=profile.profile_strength,
    )
