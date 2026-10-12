"""git-eval: отдельный микросервис оценки кода в git-репозитории.

POST /v1/evaluations        — поставить репозиторий в очередь (202)
GET  /v1/evaluations/{id}   — статус и результат
GET  /healthz               — проверка живости и доступных инструментов
"""
from __future__ import annotations

import hmac
import shutil
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .security import UrlRejected, validate_callback, validate_ref, validate_repo_url
from .store import Store
from .worker import Worker


class RubricPoint(BaseModel):
    point: str = Field(max_length=300)
    keywords: list[str] = Field(max_length=20)
    min_hits: int = Field(default=1, ge=1, le=20)
    weight: float = Field(default=1.0, gt=0, le=10)


class EvaluationIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=100, description="Ваш идентификатор (например, id назначенного задания)")
    repo_url: str = Field(max_length=300)
    ref: str | None = Field(default=None, max_length=100, description="Ветка или тег; по умолчанию — ветка по умолчанию")
    language: str | None = Field(default=None, pattern="^(python|java|sql|go|javascript|typescript|kotlin|csharp)$")
    rubric: list[RubricPoint] = Field(default_factory=list, max_length=30)
    expected_author: str | None = Field(default=None, max_length=100, description="Имя/e-mail автора для проверки авторства коммитов")
    weights: dict[str, float] | None = Field(default=None, description="Переопределение весов анализаторов")
    callback_url: str | None = Field(default=None, max_length=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if not s.api_key or not s.webhook_secret:
        raise RuntimeError("Задайте GITEVAL_API_KEY и GITEVAL_WEBHOOK_SECRET")
    app.state.settings = s
    app.state.store = Store(s.db_path)
    app.state.worker = Worker(app.state.store, s)
    app.state.worker.recover()
    yield
    app.state.worker.pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="git-eval", version="1.0.0", lifespan=lifespan)


def auth(x_api_key: str = Header(default="")) -> None:
    key = get_settings().api_key
    if not key or not hmac.compare_digest(x_api_key, key):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _out(row: dict) -> dict:
    return {"id": row["id"], "external_id": row["external_id"], "status": row["status"], "result": row["result"],
            "error": row["error"], "callback_status": row["callback_status"],
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


@app.post("/v1/evaluations", status_code=202, dependencies=[Depends(auth)])
def create_evaluation(body: EvaluationIn):
    s: Settings = app.state.settings
    store: Store = app.state.store
    try:                                    # быстрая проверка до постановки в очередь: плохой URL — сразу 422
        url = validate_repo_url(body.repo_url, s)
        ref = validate_ref(body.ref)
        callback = validate_callback(body.callback_url, s)
    except UrlRejected as e:
        raise HTTPException(status_code=422, detail=str(e))

    existing = store.find(body.external_id, url, ref)       # идемпотентность по (external_id, repo_url, ref)
    if existing and existing["status"] != "failed":
        return _out(existing)

    req = body.model_dump()
    req["repo_url"], req["ref"] = url, ref
    if existing:                                            # повторный запрос после ошибки = перезапуск
        eid = existing["id"]
        store.requeue(eid, req, callback)
    else:
        eid = store.create(req, url, ref, callback)
    app.state.worker.enqueue(eid)
    return _out(store.get(eid))


@app.get("/v1/evaluations/{eid}", dependencies=[Depends(auth)])
def get_evaluation(eid: str):
    row = app.state.store.get(eid)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _out(row)


@app.get("/healthz")
def healthz():
    s: Settings = app.state.settings
    return {"status": "ok", "git": bool(shutil.which("git")), "ruff": bool(shutil.which("ruff")),
            "sandbox_enabled": s.sandbox_enabled}
