"""Единый формат ошибок API: {"detail", "code", "errors"?, "request_id"?}. Поле detail сохранено для совместимости."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("app")


class DomainError(Exception):
    """Ожидаемая бизнес-ошибка (кулдауны, недопустимые переходы статусов и т.п.)."""

    def __init__(self, code: str, detail: str, status_code: int = 409, *, available_at: datetime | None = None,
                 errors: list[dict[str, Any]] | None = None):
        super().__init__(detail)
        self.code, self.detail, self.status_code = code, detail, status_code
        self.available_at, self.errors = available_at, errors


def _body(request: Request, detail: Any, code: str, **extra: Any) -> dict[str, Any]:
    body = {"detail": detail, "code": code, "request_id": getattr(request.state, "request_id", None)}
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):  # noqa: ANN001
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(
            _body(request, exc.detail, exc.code, available_at=exc.available_at, errors=exc.errors)))

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, headers=getattr(exc, "headers", None),
                            content=jsonable_encoder(_body(request, exc.detail, f"HTTP_{exc.status_code}")))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=jsonable_encoder(
            _body(request, exc.errors(), "VALIDATION_ERROR")))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        log.exception("unhandled error request_id=%s path=%s", getattr(request.state, "request_id", None), request.url.path)
        return JSONResponse(status_code=500, content=_body(request, "Internal server error", "INTERNAL_ERROR"))
