import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.endpoint import router as endpoint_router
from app.api.practice import router as practice_router
from app.api.learning import router as learning_router
from app.api.rewards import router as rewards_router
from app.chat_hub import chat_hub
from app.core import errors
from app.core.config import settings
from app.db.session import SessionLocal
from app.services import maintenance
from app.tasks.rag.gigachat import GigaChatError
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")


async def _background_loop() -> None:
    """Лёгкий фоновый цикл (без Celery/Redis): истечения раз в 5 минут, пересчёт силы профилей раз в сутки."""
    last_daily = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        try:
            now = datetime.now(timezone.utc)
            daily = now - last_daily > timedelta(hours=24)
            async with SessionLocal() as db:
                res = await maintenance.run_cycle(db, daily=daily)
            if daily:
                last_daily = now
            if any(res.values()):
                log.info("maintenance: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("maintenance cycle failed")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await chat_hub.start(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    task = asyncio.create_task(_background_loop()) if settings.background_jobs_enabled else None
    try:
        yield
    finally:
        await chat_hub.close()
        if task:
            task.cancel()


app = FastAPI(title=settings.app_name, version="1.1.0", docs_url="/docs", openapi_url="/openapi.json", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)
errors.install(app)

@app.exception_handler(GigaChatError)
async def gigachat_error(request,exc):
    return JSONResponse(status_code=503,content={'detail':str(exc)})
app.include_router(api_router)
app.include_router(endpoint_router)
app.include_router(practice_router)
app.include_router(learning_router)
app.include_router(rewards_router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "code_exec_enabled": settings.code_exec_enabled}

from fastapi.openapi.docs import get_swagger_ui_html

@app.get('/api/openapi.json', include_in_schema=False)
async def endpoint_openapi():
    return app.openapi()

@app.get('/api/docs', include_in_schema=False)
async def endpoint_docs():
    return get_swagger_ui_html(openapi_url='/api/openapi.json', title='FSP API')
