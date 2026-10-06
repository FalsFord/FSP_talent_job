import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentAnswer, AssessmentQuestion, AssessmentSession, SessionStatus, SessionType
from app.models.candidate import CandidateProfile
from app.models.reference import Grade
from app.services.category_service import ensure_category
from app.services.profile_service import refresh_candidate_search_index


PASS_THRESHOLD = 0.65


async def start_onboarding_session(
    db: AsyncSession,
    candidate: CandidateProfile,
    specialization_id: uuid.UUID,
    declared_grade_id: uuid.UUID,
    session_type: SessionType = SessionType.onboarding,
) -> AssessmentSession:
    active = await db.execute(
        select(AssessmentSession).where(
            AssessmentSession.candidate_id == candidate.id,
            AssessmentSession.status == SessionStatus.in_progress,
        )
    )
    if active.scalar_one_or_none():
        raise ValueError("ACTIVE_SESSION")

    q_result = await db.execute(
        select(AssessmentQuestion).where(
            AssessmentQuestion.specialization_id == specialization_id,
            AssessmentQuestion.grade_id == declared_grade_id,
        )
    )
    questions = list(q_result.scalars().all())
    if len(questions) < 3:
        q_result = await db.execute(select(AssessmentQuestion).limit(6))
        questions = list(q_result.scalars().all())
    random.shuffle(questions)
    picked = questions[: min(5, len(questions))]
    if not picked:
        raise ValueError("NO_QUESTIONS")

    session = AssessmentSession(
        candidate_id=candidate.id,
        session_type=session_type,
        declared_grade_id=declared_grade_id,
        specialization_id=specialization_id,
        question_ids=[str(q.id) for q in picked],
    )
    db.add(session)
    candidate.declared_grade_id = declared_grade_id
    candidate.specialization_id = specialization_id
    await db.flush()
    return session


async def submit_session(db: AsyncSession, session: AssessmentSession, answers: dict[str, dict]) -> AssessmentSession:
    if session.status != SessionStatus.in_progress:
        raise ValueError("SESSION_NOT_ACTIVE")

    correct = 0
    total = len(session.question_ids)
    for qid_str in session.question_ids:
        qid = uuid.UUID(qid_str)
        question = await db.get(AssessmentQuestion, qid)
        if not question:
            continue
        ans = answers.get(qid_str, {})
        is_correct = _check_answer(question, ans)
        db.add(
            AssessmentAnswer(
                session_id=session.id,
                question_id=qid,
                answer=ans,
                is_correct=is_correct,
            )
        )
        if is_correct:
            correct += 1

    score = correct / total if total else 0.0
    passed = score >= PASS_THRESHOLD
    session.score = score
    session.passed = passed
    session.status = SessionStatus.submitted
    session.submitted_at = datetime.now(timezone.utc)

    outcome_grade_id = session.declared_grade_id
    if not passed:
        grade = await db.get(Grade, session.declared_grade_id)
        lower = await db.execute(select(Grade).where(Grade.level == max(0, grade.level - 1)))
        lower_grade = lower.scalar_one_or_none()
        if lower_grade:
            outcome_grade_id = lower_grade.id

    session.outcome_grade_id = outcome_grade_id
    candidate = await db.get(CandidateProfile, session.candidate_id)
    if candidate:
        candidate.confirmed_grade_id = outcome_grade_id
        cat = await ensure_category(db, session.specialization_id, outcome_grade_id)
        candidate.category_id = cat.id
        candidate.profile_strength = max(candidate.profile_strength, 40 + score * 40)
        candidate.onboarding_completed = True
        candidate.grade_last_changed_at = datetime.now(timezone.utc)
        await refresh_candidate_search_index(db, candidate)
    await db.flush()
    return session


def _check_answer(question: AssessmentQuestion, answer: dict) -> bool:
    expected = question.correct_answer.get("value")
    given = answer.get("value")
    if expected is None:
        return False
    if isinstance(expected, list):
        return set(expected) == set(given or [])
    return str(expected).strip().lower() == str(given).strip().lower()
