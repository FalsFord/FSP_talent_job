"""Регулярные короткие задания от работодателя (ТЗ: «решить или предложить подход к решению»).
Результат влияет на актуальность профиля (task_ratio → сила профиля) и даёт работодателю свежий сигнал."""
from __future__ import annotations

import random
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateProfile
from app.models.platform import EmployerTask, TaskAssignment
from app.services import knowledge_service as ks
from app.services.notification_service import notify
from app.services.strength_service import recompute_strength
from app.tasks.generators import REGISTRY
from app.tasks.grading import score_rubric
from app.tasks.types import ContextPack


async def draft_from_context(db: AsyncSession, *, language: str, grade: str, context_text: str, seed: int | None = None) -> dict:
    """RAG-черновик задания «опишите подход»: retrieval по описанию потребности → выбор архетипа → условие и рубрика.
    Работодатель может отредактировать условие и рубрику перед сохранением."""
    seed = seed if seed is not None else secrets.randbits(31)
    try:
        ctx = await ks.retrieve_context(db, query=f"{context_text} {language} {grade}", language=language, grade=grade)
    except Exception:  # noqa: BLE001
        ctx = ContextPack(query=context_text)
    ctx.text = f"{ctx.text}\n{context_text}"          # описание потребности тоже влияет на выбор архетипа
    gen = REGISTRY[f"approach.{language}"]
    spec = gen.build(random.Random(seed), ctx, grade if grade in ("middle", "senior", "lead") else "middle", seed)
    return {"title": spec.public["title"].capitalize(), "statement": spec.statement, "language": language,
            "rubric": [{"point": r["point"], "keywords": r["keywords"]} for r in spec.private["rubric"]],
            "sources": spec.sources, "seed": seed}


def normalize_rubric(raw: list[dict]) -> list[dict]:
    return [{"point": str(r["point"])[:300], "keywords": [str(k).lower() for k in r.get("keywords", [])][:12],
             "min_hits": 1, "weight": 1.0} for r in raw if r.get("point") and r.get("keywords")]


async def assign(db: AsyncSession, task: EmployerTask, candidate_ids: list | None, top_n: int) -> int:
    q = select(CandidateProfile).where(CandidateProfile.onboarding_completed == True,  # noqa: E712
                                       CandidateProfile.is_discoverable == True)  # noqa: E712
    if candidate_ids:
        q = q.where(CandidateProfile.id.in_(candidate_ids))
    else:
        if task.specialization_id:
            q = q.where(CandidateProfile.specialization_id == task.specialization_id)
        if task.grade_id:
            q = q.where(CandidateProfile.confirmed_grade_id == task.grade_id)
        q = q.order_by(CandidateProfile.profile_strength.desc()).limit(top_n)
    cands = (await db.execute(q)).scalars().all()
    existing = set((await db.execute(select(TaskAssignment.candidate_id).where(TaskAssignment.task_id == task.id))).scalars().all())
    n = 0
    for c in cands:
        if c.id in existing:
            continue
        db.add(TaskAssignment(task_id=task.id, candidate_id=c.id))
        await notify(db, c.user_id, "task_assigned", "Новое задание от работодателя", task.title, {"task_id": str(task.id)})
        n += 1
    await db.flush()
    return n


async def _update_task_ratio(db: AsyncSession, c: CandidateProfile, score: float) -> None:
    c.task_ratio = score if c.task_ratio is None else round(0.5 * c.task_ratio + 0.5 * score, 4)   # сглаживание
    await recompute_strength(db, c)


async def submit(db: AsyncSession, a: TaskAssignment, task: EmployerTask, c: CandidateProfile, answer: str) -> TaskAssignment:
    from datetime import datetime, timezone

    a.answer, a.status, a.submitted_at = answer, "submitted", datetime.now(timezone.utc)
    if task.rubric:
        a.auto_score, _ = score_rubric(answer, task.rubric)
        await _update_task_ratio(db, c, a.auto_score)
    return a


async def review(db: AsyncSession, a: TaskAssignment, c: CandidateProfile, score: float, task_title: str) -> None:
    a.reviewer_score, a.status = score, "reviewed"
    await _update_task_ratio(db, c, score)       # оценка работодателя приоритетнее автооценки (усредняется поверх)
    await notify(db, c.user_id, "task_reviewed", "Ваше решение оценено", task_title, {"assignment_id": str(a.id)})
