"""Скопируйте в основной бэкенд: app/services/git_eval_client.py

Нужны поля в app/core/config.py (Settings):
    git_eval_url: str = ""                  # http://git-eval:9000 ; пусто = функция выключена
    git_eval_key: str = ""
    git_eval_webhook_secret: str = ""
    git_eval_callback_base: str = "http://api:8000"
"""
from __future__ import annotations

import hashlib
import hmac
import time
from uuid import UUID

import httpx

from app.core.config import settings


async def submit_evaluation(*, assignment_id: UUID, repo_url: str, ref: str | None, rubric: list[dict] | None,
                            language: str | None, expected_author: str | None = None) -> tuple[str, str | None]:
    """Возвращает (статус, пояснение): 'queued' | 'rejected' (плохой URL) | 'unavailable' (сервис недоступен/выключен)."""
    if not settings.git_eval_url:
        return "unavailable", "git-eval не настроен"
    payload = {
        "external_id": str(assignment_id),
        "repo_url": repo_url,
        "ref": ref,
        "language": language,
        "rubric": rubric or [],
        "expected_author": expected_author,
        "callback_url": f"{settings.git_eval_callback_base}/api/v1/internal/git-eval/callback",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{settings.git_eval_url}/v1/evaluations", json=payload,
                             headers={"X-API-Key": settings.git_eval_key})
    except httpx.HTTPError:
        return "unavailable", "git-eval недоступен"
    if r.status_code in (200, 202):
        return "queued", None
    if r.status_code == 422:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        return "rejected", detail if isinstance(detail, str) else "Некорректный адрес репозитория"
    return "unavailable", f"git-eval ответил HTTP {r.status_code}"


def verify_signature(timestamp: str, body: bytes, signature: str, max_age_s: int = 300) -> bool:
    """Проверка подписи вебхука: sha256 HMAC от '<timestamp>.<тело>' общим секретом + защита от повторов по времени."""
    try:
        if abs(time.time() - int(timestamp)) > max_age_s:
            return False
    except ValueError:
        return False
    expected = "sha256=" + hmac.new(settings.git_eval_webhook_secret.encode(), timestamp.encode() + b"." + body,
                                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
