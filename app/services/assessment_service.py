"""Тестирование кандидата: старт попытки, автосохранение, сдача, решение по грейду.

Бизнес-правила (ТЗ): грейд не понижается принудительно; смена подтверждённого грейда — не чаще раза в
grade_change_cooldown_days; кандидат, не прошедший тест на заявленный уровень, может сразу пройти тест ниже."""
from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import DomainError
from app.domain import grade_policy as gp
from app.models.assessment import AssessmentSession, SessionStatus, SessionType
from app.models.candidate import CandidateProfile, CandidateSkill, SkillSource, SkillStatus
from app.models.reference import Grade, Skill, Specialization
from app.models.tasks import AssessmentEvent, GeneratorStat, TaskInstance, TaskItem
from app.services import task_service
from app.services.category_service import ensure_category
from app.services.notification_service import notify
from app.services.profile_service import refresh_candidate_search_index
from app.services.strength_service import recompute_strength
from app.tasks.grading import grade_answer
from app.tasks.types import Kind

_EXEC_KINDS = (Kind.SQL_QUERY, Kind.CODE_FUNCTION)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_overdue(s: AssessmentSession, now: datetime) -> bool:
    if s.status != SessionStatus.in_progress:
        return False
    if s.deadline_at:
        return now > s.deadline_at + timedelta(seconds=settings.session_grace_seconds)
    # попытки, начатые прежней версией (без дедлайна), не должны блокировать новые тесты навсегда
    return bool(s.started_at) and now - s.started_at > timedelta(hours=2)


async def _expire_if_overdue(db: AsyncSession, s: AssessmentSession, now: datetime) -> bool:
    if _is_overdue(s, now):
        s.status = SessionStatus.expired
        s.result = "fail"
        s.decision = {"code": "EXPIRED", "next_step": "retry_later"}
        return True
    return False


async def get_status(db: AsyncSession, c: CandidateProfile) -> dict:
    """Сводка для личного кабинета: категория, срок подтверждения, доступные действия и даты кулдаунов."""
    now = _now()
    confirmed = await db.get(Grade, c.confirmed_grade_id) if c.confirmed_grade_id else None
    level = confirmed.level if confirmed else None

    def elig(purpose: str, target_level: int | None):
        return gp.check_start(now, purpose=purpose, confirmed_level=level, grade_changed_at=c.grade_last_changed_at,
                              last_attempt_same_target_at=None, last_expired_at=None, last_micro_at=c.last_micro_at,
                              cooldown_days=settings.grade_change_cooldown_days, retake_days=settings.retake_cooldown_days)
    change = elig("up", None) if level is not None else None
    micro = elig("micro", level)
    return {
        "confirmed_grade_id": c.confirmed_grade_id,
        "verification_status": gp.verification_status(now, c.grade_valid_until),
        "valid_until": c.grade_valid_until,
        "grade_change_available": bool(change.allowed) if change else None,
        "grade_change_available_at": change.available_at if change else None,
        "micro_test_due": bool(micro.allowed),
        "micro_test_available_at": micro.available_at,
        "languages": c.languages or [],
        "code_tasks_enabled": settings.code_exec_enabled,
    }


async def start_session(db: AsyncSession, c: CandidateProfile, *, specialization_id: uuid.UUID | None,
                        target_grade_id: uuid.UUID | None, languages: list[str] | None,
                        purpose: str | None) -> AssessmentSession:
    now = _now()
    active = (await db.execute(select(AssessmentSession).where(AssessmentSession.candidate_id == c.id,
                                                                AssessmentSession.status == SessionStatus.in_progress))).scalars().all()
    for a in active:
        if not await _expire_if_overdue(db, a, now):
            raise DomainError("ACTIVE_SESSION", "Есть незавершённая попытка тестирования", 409)
    await db.flush()

    confirmed = await db.get(Grade, c.confirmed_grade_id) if c.confirmed_grade_id else None
    confirmed_level = confirmed.level if confirmed else None
    is_micro = purpose == "micro"
    if is_micro:
        if not confirmed or not c.specialization_id:
            raise DomainError("NOT_CATEGORIZED", "Мини-тест доступен после присвоения категории", 409)
        specialization_id, target_grade_id = c.specialization_id, confirmed.id
    if not specialization_id or not target_grade_id:
        raise DomainError("VALIDATION_ERROR", "Нужны specialization_id и declared_grade_id", 422)
    if c.specialization_id and c.onboarding_completed and specialization_id != c.specialization_id:
        raise DomainError("SPECIALIZATION_LOCKED", "Смена специализации после категоризации пока не поддерживается", 409)

    target = await db.get(Grade, target_grade_id)
    spec = await db.get(Specialization, specialization_id)
    if not target or not spec:
        raise DomainError("NOT_FOUND", "Специализация или грейд не найдены", 404)
    purpose = purpose or gp.infer_purpose(confirmed_level, target.level)

    # --- ограничения по времени (политика грейда) ---
    past = (await db.execute(select(AssessmentSession).where(
        AssessmentSession.candidate_id == c.id, AssessmentSession.purpose != "micro",
        AssessmentSession.status.in_([SessionStatus.submitted, SessionStatus.expired])))).scalars().all()
    same = [p.started_at for p in past if p.declared_grade_id == target.id]
    expired = [p.started_at for p in past if p.status == SessionStatus.expired]
    elig = gp.check_start(now, purpose=purpose, confirmed_level=confirmed_level, grade_changed_at=c.grade_last_changed_at,
                          last_attempt_same_target_at=max(same) if same else None,
                          last_expired_at=max(expired) if expired else None, last_micro_at=c.last_micro_at,
                          cooldown_days=settings.grade_change_cooldown_days, retake_days=settings.retake_cooldown_days,
                          expired_retry_hours=settings.expired_retry_hours)
    if not elig.allowed:
        raise DomainError(elig.code or "NOT_ALLOWED", elig.message, 409, available_at=elig.available_at)

    langs = task_service.sanitize_languages(languages) or task_service.sanitize_languages(c.languages) \
        or task_service.default_languages(spec.code)
    if not langs:
        raise DomainError("NO_TASKS_FOR_SPECIALIZATION",
                          "Для этой специализации пока нет автоматических заданий (поддерживаются Python, Java, SQL). "
                          "Передайте languages или выберите другую специализацию.", 422)
    seed = secrets.randbits(62)
    n = settings.test_items_micro if is_micro else settings.test_items_initial
    recent = await task_service.recent_generator_ids(db, c.id)
    specs, _prov = await task_service.compose_specs(db, seed=seed, grade=target.code, languages=langs, spec_name=spec.name,
                                                    purpose=purpose, n_items=n, recent=recent)
    if len(specs) < max(3, n // 2):
        raise DomainError("NO_TASKS", "В банке недостаточно заданий для этого языка и грейда", 503)

    session = AssessmentSession(candidate_id=c.id, session_type=SessionType.onboarding if purpose == "onboarding" else SessionType.retest,
                                declared_grade_id=target.id, specialization_id=spec.id, purpose=purpose, languages=langs,
                                question_ids=[], integrity=[])
    db.add(session)
    await db.flush()
    await task_service.persist_instances(db, session, specs)
    session.deadline_at = now + timedelta(seconds=session.time_limit_s or 1800)
    c.languages = langs
    if purpose != "micro":
        c.declared_grade_id, c.specialization_id = target.id, spec.id
    await db.flush()
    return session


async def get_instances(db: AsyncSession, session: AssessmentSession) -> list[TaskInstance]:
    return list((await db.execute(select(TaskInstance).where(TaskInstance.session_id == session.id)
                                  .order_by(TaskInstance.position))).scalars().all())


def public_view(inst: TaskInstance) -> dict:
    """Что видит кандидат. Ключи ответов и скрытые тесты (private) сюда не попадают никогда."""
    return {"id": inst.id, "prompt": inst.statement, "question_type": inst.kind, "kind": inst.kind,
            "language": inst.language, "topic": inst.topic, "time_limit_s": inst.time_limit_s,
            "options": {"choices": inst.public.get("options")} if inst.public.get("options") else None,
            "public": {k: v for k, v in inst.public.items() if k != "options"}, "answer": (inst.answer or {}).get("value")}


async def save_answer(db: AsyncSession, session: AssessmentSession, instance_id: uuid.UUID, value) -> None:
    now = _now()
    if session.status != SessionStatus.in_progress:
        raise DomainError("SESSION_NOT_ACTIVE", "Попытка уже завершена", 409)
    if session.deadline_at and now > session.deadline_at + timedelta(seconds=settings.session_grace_seconds):
        raise DomainError("SESSION_EXPIRED", "Время попытки истекло", 409)
    inst = await db.get(TaskInstance, instance_id)
    if not inst or inst.session_id != session.id:
        raise DomainError("NOT_FOUND", "Задание не найдено", 404)
    inst.answer, inst.answered_at = {"value": value}, now


async def record_event(db: AsyncSession, session: AssessmentSession, type_: str, meta: dict | None) -> None:
    if session.status == SessionStatus.in_progress:
        db.add(AssessmentEvent(session_id=session.id, type=type_[:32], meta=meta or {}))


async def _grade_all(insts: list[TaskInstance]) -> None:
    sem = asyncio.Semaphore(4)

    async def one(i: TaskInstance) -> None:
        if i.answer is None:
            i.score, i.details, i.graded = 0.0, {"error": "NO_ANSWER"}, True
            return
        args = (i.kind, i.language, i.public, i.private, i.answer)
        async with sem:
            if i.kind in _EXEC_KINDS:     # SQL/код — синхронные и потенциально долгие: выносим в поток
                res = await asyncio.to_thread(lambda: grade_answer(*args, code_exec_enabled=settings.code_exec_enabled))
            else:
                res = grade_answer(*args, code_exec_enabled=settings.code_exec_enabled)
        i.score, i.details, i.graded = res.score, {**res.details, **({"needs_review": True} if res.needs_review else {})}, True

    await asyncio.gather(*(one(i) for i in insts))


async def _verify_skills(db: AsyncSession, c: CandidateProfile, per_lang: dict[str, float], now: datetime, micro: bool) -> None:
    for lang, ratio in per_lang.items():
        res = await db.execute(select(Skill).where(Skill.slug == lang))
        skill = res.scalar_one_or_none()
        if not skill:
            skill = Skill(name=lang, slug=lang)
            db.add(skill)
            await db.flush()
        cs = (await db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == c.id,
                                                            CandidateSkill.skill_id == skill.id))).scalar_one_or_none()
        if ratio >= 0.6:
            if not cs:
                cs = CandidateSkill(candidate_id=c.id, skill_id=skill.id)
                db.add(cs)
            cs.source, cs.status, cs.verified_at = SkillSource.test_verified, SkillStatus.verified, now
        elif cs and micro and ratio < 0.4 and cs.status == SkillStatus.verified:
            cs.status = SkillStatus.stale          # мини-тест выявил просадку: навык «требует повторной проверки»


async def submit_session(db: AsyncSession, session: AssessmentSession, answers: dict[str, dict] | None) -> dict:
    now = _now()
    if session.status != SessionStatus.in_progress:
        raise DomainError("SESSION_NOT_ACTIVE", "Попытка уже завершена", 409)
    if await _expire_if_overdue(db, session, now):
        return {"expired": True}
    insts = await get_instances(db, session)
    for key, val in (answers or {}).items():          # ответы из тела запроса дополняют автосохранённые
        for i in insts:
            if str(i.id) == key and isinstance(val, dict) and "value" in val:
                i.answer, i.answered_at = {"value": val["value"]}, i.answered_at or now
    await _grade_all(insts)

    items = [(i.score, i.weight) for i in insts]
    ratio, scored_frac = gp.session_ratio(items)
    events = (await db.execute(select(AssessmentEvent).where(AssessmentEvent.session_id == session.id))).scalars().all()
    flags: list[str] = []
    if sum(1 for e in events if e.type == "blur") > 5:
        flags.append("FOCUS_LOSS")
    elapsed = (now - session.started_at).total_seconds() if session.started_at else 0
    if session.time_limit_s and elapsed < 0.12 * session.time_limit_s and ratio > 0.9:
        flags.append("TOO_FAST")
    confidence = gp.confidence_from(scored_frac, flags)
    result = gp.classify_result(ratio, confidence)

    c = await db.get(CandidateProfile, session.candidate_id)
    target = await db.get(Grade, session.declared_grade_id)
    confirmed = await db.get(Grade, c.confirmed_grade_id) if c.confirmed_grade_id else None
    dec = gp.decide(purpose=session.purpose, target_level=target.level, confirmed_level=confirmed.level if confirmed else None,
                    result=result, ratio=ratio)

    per_lang: dict[str, list[tuple[float, float]]] = {}
    for i in insts:
        if i.score is not None:
            per_lang.setdefault(i.language, []).append((i.score, i.weight))
    lang_ratio = {l: gp.session_ratio([(s, w) for s, w in v])[0] for l, v in per_lang.items()}

    outcome_grade_id = c.confirmed_grade_id
    if dec.changed and dec.new_level is not None:
        outcome_grade_id = target.id
        c.confirmed_grade_id = target.id
        cat = await ensure_category(db, session.specialization_id, target.id)
        c.category_id = cat.id
        c.onboarding_completed = True
        c.grade_last_changed_at = c.grade_confirmed_at = now
        c.grade_valid_until = now + timedelta(days=gp.VALIDITY_DAYS)
        c.last_test_ratio = ratio
    elif dec.reconfirmed:
        c.grade_confirmed_at, c.grade_valid_until, c.last_test_ratio = now, now + timedelta(days=gp.VALIDITY_DAYS), ratio
    if session.purpose == "micro":
        c.last_micro_at = now
    if result == "pass" or session.purpose == "micro":
        await _verify_skills(db, c, lang_ratio, now, micro=session.purpose == "micro")

    session.status, session.submitted_at = SessionStatus.submitted, now
    session.score, session.scaled_score, session.confidence = ratio, round(ratio * 100, 1), confidence
    session.result, session.passed, session.integrity = result, result == "pass", flags
    session.outcome_grade_id = outcome_grade_id
    lower = None
    if dec.next_step == "try_lower" and target.level > 0:
        lower = (await db.execute(select(Grade).where(Grade.level == target.level - 1))).scalar_one_or_none()
    session.decision = {"code": dec.code, "next_step": dec.next_step, "lower_grade_id": str(lower.id) if lower else None}

    for i in insts:       # статистика для калибровки сложности и контроля экспозиции
        stat = await db.get(GeneratorStat, i.generator_id)
        if stat and i.score is not None:
            stat.scored, stat.score_sum = stat.scored + 1, stat.score_sum + i.score
        if i.generator_id.startswith("item:") and i.score is not None:
            item = await task_service.find_item(db, i.generator_id[5:])
            if item:
                item.answered_count += 1
                item.correct_count += int(i.score >= 0.999)

    await recompute_strength(db, c, now)
    await refresh_candidate_search_index(db, c)
    cand_user_id = c.user_id
    await notify(db, cand_user_id, "assessment_result", "Результат тестирования",
                 f"Результат: {session.scaled_score}% ({result}).", {"session_id": str(session.id), "code": dec.code})
    await db.flush()
    return {"ratio": ratio, "result": result, "confidence": confidence, "decision": dec, "lang_ratio": lang_ratio,
            "flags": flags, "lower_grade_id": lower.id if lower else None, "instances": insts, "expired": False}
