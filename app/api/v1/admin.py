"""Администрирование конвейера заданий и корпуса знаний (только роль admin)."""
import asyncio
import random
import secrets
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_roles
from app.core.errors import DomainError
from app.models.tasks import GeneratorStat, TaskItem
from app.models.user import User, UserRole
from app.services import knowledge_service as ks
from app.tasks.generators import ALL_GENERATORS, REGISTRY, eligible
from app.tasks.rag import llm as llm_mod
from app.tasks.runners.code_runner import java_available
from app.tasks.types import ContextPack
from app.tasks.validation import similarity, validate_bank, validate_spec

router = APIRouter(prefix="/admin", tags=["admin"])
_admin = require_roles(UserRole.admin)


class PreviewIn(BaseModel):
    language: str = Field(pattern="^(python|java|sql)$")
    grade: str = Field(pattern="^(intern|junior|middle|senior|lead)$")
    generator_id: str | None = None
    seed: int | None = None
    query: str | None = Field(default=None, description="текст для retrieval (например, описание вакансии)")


class ValidateIn(BaseModel):
    seeds: int = Field(default=10, ge=1, le=50)
    skip_code_exec: bool = True


class IngestIn(BaseModel):
    path: str | None = None
    builtin_only: bool = False


class DraftIn(BaseModel):
    language: str = Field(pattern="^(python|java|sql)$")
    grade: str = Field(pattern="^(intern|junior|middle|senior|lead)$")
    topic: str = Field(min_length=3, max_length=64)
    count: int = Field(default=3, ge=1, le=10)


class ItemStatusIn(BaseModel):
    status: str = Field(pattern="^(draft|active|retired)$")


def get_llm():
    if settings.llm_base_url and settings.llm_model:
        return llm_mod.OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    return llm_mod.NullLLM()


@router.get("/tasks/generators")
async def generators(user: User = Depends(_admin)):
    return {"code_exec_enabled": settings.code_exec_enabled, "java_available": java_available(),
            "generators": [{"id": g.id, "language": g.language, "kind": g.kind, "topic": g.topic, "grades": g.grades,
                            "difficulty": g.difficulty, "needs_code_exec": g.needs_code_exec} for g in ALL_GENERATORS]}


@router.post("/tasks/preview")
async def preview(body: PreviewIn, user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    """Показывает сгенерированное задание ЦЕЛИКОМ (включая ключ/тесты) и результат автоматической валидации."""
    seed = body.seed if body.seed is not None else secrets.randbits(31)
    if body.generator_id:
        gen = REGISTRY.get(body.generator_id)
        if not gen:
            raise DomainError("NOT_FOUND", "Генератор не найден", 404)
    else:
        pool = eligible(body.language, body.grade, code_exec=True, java_ok=java_available())
        if not pool:
            raise DomainError("NO_GENERATORS", "Нет генераторов для языка и грейда", 404)
        gen = random.Random(seed).choice(pool)
    try:
        ctx = await ks.retrieve_context(db, query=body.query or f"{body.language} {body.grade}", language=body.language, grade=body.grade)
    except Exception:  # noqa: BLE001
        ctx = ContextPack()
    spec = gen.build(random.Random(seed), ctx, body.grade, seed)
    rep = await asyncio.to_thread(validate_spec, spec, [c["text"] for c in ctx.chunks])
    return {"generator_id": gen.id, "seed": seed, "task": {**spec.public_dict(), "private": spec.private},
            "context": {"sources": ctx.sources, "topic_hints": ctx.topic_hints}, "validation": asdict(rep)}


@router.post("/tasks/validate-bank")
async def validate_all(body: ValidateIn, user: User = Depends(_admin)):
    report = await asyncio.to_thread(lambda: validate_bank(ALL_GENERATORS, range(body.seeds), skip_code_exec=body.skip_code_exec))
    bad = {k: v for k, v in report.items() if v["built_ok"] < v["attempts"]}
    return {"generators": report, "failed_generators": list(bad)}


@router.get("/knowledge/stats")
async def knowledge_stats(user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    return await ks.knowledge_stats(db)


@router.post("/knowledge/ingest")
async def knowledge_ingest(body: IngestIn, user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    out = {"builtin": await ks.ingest_builtin(db)}
    if not body.builtin_only:
        base = Path(settings.knowledge_dir).resolve()
        root = Path(body.path).resolve() if body.path else base
        if base != root and base not in root.parents:     # защита от выхода за пределы разрешённого каталога
            raise DomainError("PATH_NOT_ALLOWED", "Путь должен находиться внутри KNOWLEDGE_DIR", 400)
        if not root.is_dir():
            raise DomainError("CORPUS_NOT_FOUND", f"Каталог корпуса не найден: {root}", 404)
        out["corpus"] = await ks.ingest_directory(db, root)
    out["stats"] = await ks.knowledge_stats(db)
    return out


@router.post("/tasks/drafts", status_code=201)
async def make_drafts(body: DraftIn, user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    """Черновики вопросов через LLM (RAG: контекст из корпуса). Черновики сохраняются со статусом draft и
    не попадают к кандидатам, пока администратор не утвердит их."""
    ctx = await ks.retrieve_context(db, query=f"{body.topic} {body.language} {body.grade}", language=body.language, grade=body.grade)
    try:
        data = await get_llm().complete_json(llm_mod.DRAFT_SYSTEM, llm_mod.build_draft_prompt(
            body.language, body.grade, body.topic, ctx.text, body.count))
    except Exception as e:  # noqa: BLE001
        raise DomainError("LLM_UNAVAILABLE", f"LLM недоступен: {e}", 503) from e
    created, rejected = [], 0
    for it in llm_mod.validate_draft_items(data):
        if any(similarity(it["statement"], c["text"]) > 0.35 for c in ctx.chunks):    # не копируем материалы корпуса
            rejected += 1
            continue
        item = TaskItem(kind="quiz_single", language=body.language, grade=body.grade, topic=body.topic, statement=it["statement"],
                        options=it["options"], correct=it["correct"], explanation=it["explanation"], status="draft",
                        origin="llm_draft")
        db.add(item)
        created.append(item)
    await db.commit()
    return {"created": [str(i.id) for i in created], "rejected_as_too_similar": rejected, "sources": ctx.sources}


@router.get("/tasks/items")
async def items(status: str | None = None, language: str | None = None, user: User = Depends(_admin),
                db: AsyncSession = Depends(get_db)):
    q = select(TaskItem)
    if status:
        q = q.where(TaskItem.status == status)
    if language:
        q = q.where(TaskItem.language == language)
    rows = (await db.execute(q.order_by(TaskItem.created_at.desc()).limit(200))).scalars().all()
    return [{"id": i.id, "ext_id": i.ext_id, "language": i.language, "grade": i.grade, "topic": i.topic, "statement": i.statement,
             "options": i.options, "correct": i.correct, "status": i.status, "origin": i.origin, "difficulty": i.difficulty,
             "exposure": i.exposure_count, "correct_rate": (i.correct_count / i.answered_count) if i.answered_count else None}
            for i in rows]


@router.patch("/tasks/items/{item_id}")
async def set_item_status(item_id: UUID, body: ItemStatusIn, user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    item = await db.get(TaskItem, item_id)
    if not item:
        raise DomainError("NOT_FOUND", "Item not found", 404)
    item.status = body.status
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.get("/stats/generators")
async def generator_stats(user: User = Depends(_admin), db: AsyncSession = Depends(get_db)):
    """Статистика показов и средних баллов по генераторам — основа калибровки сложности и контроля экспозиции."""
    rows = (await db.execute(select(GeneratorStat).order_by(GeneratorStat.shown.desc()))).scalars().all()
    return [{"generator_id": r.generator_id, "shown": r.shown, "scored": r.scored,
             "mean_score": round(r.score_sum / r.scored, 3) if r.scored else None} for r in rows]
