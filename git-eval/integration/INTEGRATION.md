# Подключение git-eval к основному бэкенду

Основной бэкенд меняется минимально: одно новое поле, один клиент, один внутренний эндпоинт и правка `submit`.
Если `GIT_EVAL_URL` пуст, всё остаётся как раньше, а репозитории принимаются без автооценки (работодатель оценивает вручную).

> Эти патчи написаны по коду вашего бэкенда, но в основном бэкенде здесь не запускались. Проверьте на своей копии.

## 1. Секреты и compose

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # выполните дважды
```
Положите значения в `git-eval/.env` (`GITEVAL_API_KEY`, `GITEVAL_WEBHOOK_SECRET`) и в корневой `.env` основного проекта
(те же значения). Фрагмент для `docker-compose.yml` — в `integration/docker-compose.snippet.yml`.

## 2. Настройки (`app/core/config.py`)

```python
git_eval_url: str = ""                      # http://git-eval:9000 ; пусто = выключено
git_eval_key: str = ""
git_eval_webhook_secret: str = ""
git_eval_callback_base: str = "http://api:8000"
```

## 3. Новая колонка для деталей оценки

`app/models/platform.py`, класс `TaskAssignment`:
```python
eval_details: Mapped[dict | None] = mapped_column(JSONB)      # from sqlalchemy.dialects.postgresql import JSONB
```
Так как у вас подключён Alembic, создайте миграцию (`create_all` не добавляет колонки в существующие таблицы):
```python
def upgrade():
    op.add_column("task_assignments", sa.Column("eval_details", postgresql.JSONB(), nullable=True))
def downgrade():
    op.drop_column("task_assignments", "eval_details")
```
Статус `evaluating` помещается в `String(16)`, менять тип не нужно. Допустимые статусы теперь:
`assigned → evaluating → submitted → reviewed` (для текстовых ответов `evaluating` пропускается).

## 4. Клиент и приём результата

- `integration/git_eval_client.py` → `app/services/git_eval_client.py`
- `integration/internal_git_eval.py` → `app/api/v1/internal_git_eval.py`, и в `app/api/v1/router.py`:
  ```python
  from app.api.v1 import internal_git_eval
  api_router.include_router(internal_git_eval.router)
  ```

## 5. Правка отправки решения (`app/api/v1/tasks.py`)

```python
from datetime import datetime, timezone
from pydantic import model_validator
from app.services import git_eval_client

class SubmitIn(BaseModel):
    answer: str | None = Field(default=None, min_length=20, max_length=8000)
    repo_url: str | None = Field(default=None, max_length=300)
    ref: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one_of(self):
        if not (self.answer or self.repo_url):
            raise ValueError("Нужен answer или repo_url")
        return self


@router.post("/candidates/me/tasks/{assignment_id}/submit")
async def submit_task(assignment_id: UUID, body: SubmitIn, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    c = await candidate_profile(db, user.id)
    a = await db.get(TaskAssignment, assignment_id)
    if not a or a.candidate_id != c.id:
        raise DomainError("NOT_FOUND", "Assignment not found", 404)
    if a.status != "assigned":
        raise DomainError("ALREADY_SUBMITTED", "Решение уже отправлено", 409)
    t = await db.get(EmployerTask, a.task_id)

    if body.repo_url:
        # НЕ вызываем svc.submit: он считает рубрику по тексту ответа, а у нас в ответе только ссылка
        a.answer, a.status, a.submitted_at = body.repo_url, "evaluating", datetime.now(timezone.utc)
        await db.commit()                       # сначала фиксируем статус, потом просим оценку — вебхук не обгонит коммит
        state, detail = await git_eval_client.submit_evaluation(
            assignment_id=a.id, repo_url=body.repo_url, ref=body.ref, rubric=t.rubric, language=t.language)
        if state == "rejected":                 # плохая ссылка: возвращаем кандидату возможность исправить
            a.status = "assigned"
            await db.commit()
            raise DomainError("BAD_REPO_URL", detail or "Некорректный адрес репозитория", 422)
        if state == "unavailable":              # деградация: принимаем без автооценки, работодатель оценит сам
            a.status, a.eval_details = "submitted", {"error": {"code": "unavailable", "message": detail}}
            await db.commit()
        return {"id": a.id, "status": a.status, "auto_score": None}

    await svc.submit(db, a, t, c, body.answer)
    await db.commit()
    return {"id": a.id, "status": a.status, "auto_score": a.auto_score}
```

## 6. Показать результат работодателю

В `GET /employers/tasks/{task_id}/assignments` добавьте в словарь строки: `"eval_details": a.eval_details`.
Ключевые поля для интерфейса: `eval_details.score`, `.verdict`, `.flags`, `.summary` (до 6 главных замечаний)
и `.breakdown` (детализация по каждому анализатору).

## 7. Проверка сквозного сценария

1. Работодатель создаёт задание с рубрикой и назначает кандидату (как раньше).
2. Кандидат: `POST /candidates/me/tasks/{assignment_id}/submit` с `{"repo_url": "https://github.com/owner/repo"}`.
   Статус становится `evaluating`.
3. Через 5–60 секунд приходит вебхук: у задания появляются `auto_score` и `eval_details`, статус `submitted`,
   работодателю приходит уведомление `task_evaluated`.
4. Работодатель при желании ставит собственную оценку через `PATCH /employers/tasks/assignments/{id}`.

Если оценка не пришла: `GET http://git-eval:9000/v1/evaluations/<id>` (с заголовком `X-API-Key`) покажет статус и ошибку,
а `callback_status` — дошёл ли вебхук.
