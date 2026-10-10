"""Скопируйте в основной бэкенд: app/api/v1/internal_git_eval.py и подключите в router.py:

    from app.api.v1 import internal_git_eval
    api_router.include_router(internal_git_eval.router)

Эндпоинт без JWT: доверие обеспечивает HMAC-подпись. Наружу (через публичный прокси) его публиковать не нужно.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.errors import DomainError
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.platform import EmployerTask, TaskAssignment
from app.services.employer_task_service import _update_task_ratio
from app.services.git_eval_client import verify_signature
from app.services.notification_service import notify

router = APIRouter(prefix="/internal/git-eval", tags=["internal"], include_in_schema=False)


@router.post("/callback", status_code=204)
async def git_eval_callback(request: Request, db: AsyncSession = Depends(get_db),
                            x_giteval_timestamp: str = Header(default=""),
                            x_giteval_signature: str = Header(default="")):
    body = await request.body()
    if not verify_signature(x_giteval_timestamp, body, x_giteval_signature):
        raise DomainError("BAD_SIGNATURE", "Неверная подпись", 401)
    try:
        data = json.loads(body)
        assignment_id = UUID(data["external_id"])
    except (ValueError, KeyError):
        raise DomainError("BAD_PAYLOAD", "Некорректное тело запроса", 422)

    a = await db.get(TaskAssignment, assignment_id)
    if not a or a.status != "evaluating":
        return                                   # повторная доставка или уже обработано — отвечаем 204, чтобы не было ретраев
    t = await db.get(EmployerTask, a.task_id)
    c = await db.get(CandidateProfile, a.candidate_id)

    if data.get("status") == "done" and data.get("result"):
        a.auto_score = float(data["result"]["score"])
        a.eval_details = data["result"]
        await _update_task_ratio(db, c, a.auto_score)       # как и для текстовых ответов с рубрикой
    else:
        a.eval_details = {"error": data.get("error") or {"code": "unknown", "message": "Оценка не выполнена"}}
    a.status = "submitted"                      # дальше — как обычно: работодатель может выставить свою оценку

    ep = await db.get(EmployerProfile, t.employer_id) if t else None
    if ep:
        await notify(db, ep.user_id, "task_evaluated", "Репозиторий кандидата проверен", t.title,
                     {"assignment_id": str(a.id)})
    await db.commit()
