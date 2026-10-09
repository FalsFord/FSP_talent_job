"""Сборка набора заданий для попытки: RAG-контекст → банк пунктов → blueprint → экземпляры заданий."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assessment import AssessmentSession
from app.models.tasks import GeneratorStat, TaskInstance, TaskItem
from app.services import knowledge_service as ks
from app.tasks.blueprint import compose_test, session_time_limit
from app.tasks.quiz_bank import QUIZ_ITEMS
from app.tasks.runners.code_runner import java_available
from app.tasks.types import LANGUAGES, ContextPack, TaskSpec

# Специализация → языки по умолчанию (справочник из ТЗ составляет команда; здесь — основные направления).
SPEC_LANGUAGES: dict[str, list[str]] = {
    "backend": ["python", "sql"], "data": ["python", "sql"], "qa": ["python", "sql"], "devops": ["python", "sql"],
}


def default_languages(spec_code: str) -> list[str]:
    return list(SPEC_LANGUAGES.get(spec_code, []))


def sanitize_languages(langs: list[str] | None) -> list[str]:
    return [l for l in dict.fromkeys(langs or []) if l in LANGUAGES]


async def find_item(db: AsyncSession, key: str) -> TaskItem | None:
    """Пункт банка по ключу из generator_id вида 'item:<ext_id|uuid>' (у утверждённых LLM-черновиков ext_id нет)."""
    item = (await db.execute(select(TaskItem).where(TaskItem.ext_id == key))).scalar_one_or_none()
    if item:
        return item
    try:
        return await db.get(TaskItem, uuid.UUID(key))
    except ValueError:
        return None


async def load_quiz_pool(db: AsyncSession, languages: list[str], grade: str) -> list[dict]:
    rows = (await db.execute(select(TaskItem).where(TaskItem.status == "active", TaskItem.language.in_(languages),
                                                    TaskItem.grade == grade))).scalars().all()
    if rows:
        return [{"id": r.ext_id or str(r.id), "language": r.language, "grade": r.grade, "topic": r.topic,
                 "statement": r.statement, "options": r.options, "correct": r.correct,
                 "explanation": r.explanation or "", "difficulty": r.difficulty} for r in rows]
    return [i for i in QUIZ_ITEMS if i["language"] in languages and i["grade"] == grade]   # запасной вариант без сидирования


async def build_contexts(db: AsyncSession, languages: list[str], grade: str, spec_name: str,
                         extra_text: str = "") -> dict[str, ContextPack]:
    out: dict[str, ContextPack] = {}
    for lang in languages:
        q = f"{spec_name} {lang} {grade} {extra_text}".strip()
        try:
            out[lang] = await ks.retrieve_context(db, query=q, language=lang, grade=grade)
        except Exception:  # noqa: BLE001  — отсутствие корпуса/индекса не должно ломать тест
            out[lang] = ContextPack(query=q)
    return out


async def recent_generator_ids(db: AsyncSession, candidate_id, limit_sessions: int = 3) -> set[str]:
    sess = (await db.execute(select(AssessmentSession.id).where(AssessmentSession.candidate_id == candidate_id)
                             .order_by(AssessmentSession.started_at.desc()).limit(limit_sessions))).scalars().all()
    if not sess:
        return set()
    ids = (await db.execute(select(TaskInstance.generator_id).where(TaskInstance.session_id.in_(sess)))).scalars().all()
    return set(ids)


async def compose_specs(db: AsyncSession, *, seed: int, grade: str, languages: list[str], spec_name: str,
                        purpose: str, n_items: int, recent: set[str], extra_text: str = "") -> tuple[list[TaskSpec], dict]:
    contexts = await build_contexts(db, languages, grade, spec_name, extra_text)
    pool = await load_quiz_pool(db, languages, grade)
    specs = compose_test(seed=seed, grade=grade, languages=languages, n_items=n_items, purpose=purpose,
                         contexts=contexts, quiz_pool=pool, code_exec=settings.code_exec_enabled,
                         java_ok=java_available(), recent_generators=recent)
    provenance = {lang: {"sources": c.sources, "topic_hints": c.topic_hints} for lang, c in contexts.items()}
    return specs, provenance


async def persist_instances(db: AsyncSession, session: AssessmentSession, specs: list[TaskSpec]) -> list[TaskInstance]:
    out = []
    for pos, s in enumerate(specs):
        inst = TaskInstance(session_id=session.id, position=pos, generator_id=s.generator_id, kind=s.kind,
                            language=s.language, grade=s.grade, topic=s.topic, seed=s.seed, fingerprint=s.fingerprint(),
                            statement=s.statement, public=s.public, private=s.private, difficulty=s.difficulty,
                            weight=s.weight, time_limit_s=s.time_limit_s, manual_review=s.manual_review, sources=s.sources)
        db.add(inst)
        out.append(inst)
        stat = await db.get(GeneratorStat, s.generator_id)
        if not stat:
            stat = GeneratorStat(generator_id=s.generator_id, shown=0, scored=0, score_sum=0.0)
            db.add(stat)
        stat.shown += 1
        if s.generator_id.startswith("item:"):
            item = await find_item(db, s.generator_id[5:])
            if item:
                item.exposure_count += 1
    await db.flush()
    session.question_ids = [str(i.id) for i in out]
    session.time_limit_s = session_time_limit(specs, session.purpose)
    return out
