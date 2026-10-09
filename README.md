# FSP Talent Platform — Backend API

Платформа подбора IT-специалистов с ролевой моделью: **кандидаты** проходят онбординг и тестовые оценки,
**работодатели** публикуют потребности (needs) и вакансии, строят шорт-листы кандидатов по силе профиля и
приглашают их, **администраторы** управляют конвейером заданий и корпусом знаний (RAG).

- FastAPI + SQLAlchemy 2 (async) + PostgreSQL с pgvector
- JWT-авторизация, подтверждение email (опционально)
- Конвейер генерации заданий (Python / Java / SQL, грейды intern → lead) с валидацией и RAG
- Гибридный поиск кандидатов (эмбеддинги + правила ранжирования)
- Фоновые задачи (expirations, пересчёт силы профилей) — встроенный asyncio-цикл, без Celery

---

## Быстрый старт (Docker)

```bash
cp .env.example .env          # задать SECRET_KEY, при желании — SMTP и LLM
# опционально: корпус знаний для RAG
git clone https://github.com/Hexlet/ru-test-assignments data/ru-test-assignments
docker compose up --build
```

Entrypoint контейнера сам: дождётся БД → накатит миграции → засидирует справочники → загрузит корпус знаний → запустит uvicorn.

API будет доступен на `http://localhost:8000`:

| URL | Что это |
|---|---|
| `/docs` | Swagger UI (интерактивная документация) |
| `/openapi.json` | OpenAPI-схема |
| `/health` | Проверка живости (`status`, `code_exec_enabled`) |

### Локальный запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# PostgreSQL 16 + pgvector, DATABASE_URL в .env
python -m app.db.wait_for_db && python -m app.db.init_db && python -m app.db.seed
python -m app.tasks.rag.ingest   # опционально
uvicorn app.main:app --reload --port 8000
```

Для качественных эмбеддингов: `pip install -r requirements-ml.txt` и `EMBEDDING_BACKEND=fastembed`
(по умолчанию — детерминированный `hash`-бэкенд, без внешних зависимостей).

### Тесты

```bash
pytest tests/
```

---

## Аутентификация

Регистрация и логин выдают JWT (`access_token`). Дальше передавайте его в заголовке:

```
Authorization: Bearer <access_token>
```

Роли задаются при регистрации: `candidate` | `employer`. Администратор создаётся через seed.

### ВСЕ ИЗНАЧАЛЬНО СОЗДАННЫЕ ПОЛЬЗОВАТЕЛИ ИМЕЮТ ПАРОЛЬ `demo1234`

---

## Общие эндпоинты

### Service
| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Статус сервиса |

### Auth — `/api/v1/auth`
| Метод | Путь | Тело | Описание |
|---|---|---|---|
| POST | `/register` | `RegisterIn` | Регистрация, возвращает `TokenOut` (201) |
| POST | `/verify-email` | `VerifyIn` | Подтверждение email по коду |
| POST | `/resend-verification` | `ResendIn` | Повторная отправка кода (202) |
| POST | `/login` | `LoginIn` | Логин → `TokenOut` |
| GET | `/me` | — | Текущий пользователь (JWT) |

### Reference — `/api/v1/ref` (публично)
| Метод | Путь | Описание |
|---|---|---|
| GET | `/specializations` | Список специализаций |
| GET | `/grades` | Список грейдов |

### Уведомления — `/api/v1/notifications` (любая роль)
| Метод | Путь | Описание |
|---|---|---|
| GET | `?unread_only=true&limit=50` | Список уведомлений |
| POST | `/{notification_id}/read` | Отметить прочитанным (204) |
| POST | `/read-all` | Отметить все прочитанными (204) |

---

## Кандидат — `/api/v1/candidates` (роль `candidate`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/me/profile` | Профиль кандидата |
| PATCH | `/me/profile` | Обновить профиль (специализация, грейд, навыки и т.д.) |
| PATCH | `/me/privacy` | Настройки приватности |
| POST | `/me/fsp-link` | Привязать внешний FSP-аккаунт |
| DELETE | `/me/fsp-link` | Отвязать FSP-аккаунт (204) |
| GET | `/me/category` | Текущая категория/сила профиля |

## Оценки — `/api/v1/assessments` (роль `candidate`)

| Метод | Путь | Описание |
|---|---|---|
| POST | `/onboarding/start` | Начать онбординг-тест → `SessionOut` |
| POST | `/start` | Начать сессию оценки (`StartIn`) |
| GET | `/status` | Статус текущей/последней оценки |
| GET | `/sessions/{session_id}/questions` | Вопросы сессии |
| PUT | `/sessions/{session_id}/answers/{instance_id}` | Автосохранение ответа (204) |
| POST | `/sessions/{session_id}/events` | События сессии (тайминги и пр.) (204) |
| POST | `/sessions/{session_id}/submit` | Завершить сессию → `SubmitResultOut` |
| GET | `/sessions/{session_id}/result` | Результат сессии |
| GET | `/history` | История оценок |

Ограничения (настраиваются в `.env`): `GRADE_CHANGE_COOLDOWN_DAYS`, `RETAKE_COOLDOWN_DAYS`,
размеры теста `TEST_ITEMS_INITIAL` / `TEST_ITEMS_MICRO`.

## Задания кандидата — `/api/v1/tasks`
| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates/me/tasks` | Мои назначенные задания |
| POST | `/candidates/me/tasks/{assignment_id}/submit` | Отправить решение (`SubmitIn`) |

---

## Работодатель — `/api/v1/employers` (роль `employer`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/me/company` | Профиль компании |
| PATCH | `/me/company` | Обновить компанию |
| POST | `/needs` | Создать потребность (need) (201) |
| GET | `/needs` | Список потребностей |
| GET | `/needs/{need_id}/candidates` | Подобранные кандидаты (`MatchedCandidateOut`) |
| GET | `/needs/{need_id}/categories` | Рекомендации категорий |
| POST | `/needs/{need_id}/shortlist` | Построить шорт-лист (`ShortlistIn`) → `ShortlistOut` |
| GET | `/needs/{need_id}/shortlist/snapshots` | Снапшоты шорт-листов |
| GET | `/needs/{need_id}/shortlist/snapshots/{snapshot_id}` | Конкретный снапшот |
| POST | `/needs/{need_id}/task-preview` | Превью тестового задания под потребность |
| GET | `/candidates/{candidate_id}/contacts` | Контакты кандидата (с учётом приватности/траст-правил) |
| GET | `/candidates/{candidate_id}/preview` | Публичная карточка кандидата |

### Задания работодателя — `/api/v1/tasks/employers/...`
| Метод | Путь | Описание |
|---|---|---|
| POST | `/tasks/draft` | Черновик задания |
| POST | `/tasks` | Создать задание (201) |
| GET | `/tasks` | Список заданий |
| POST | `/tasks/{task_id}/assign` | Назначить кандидатам (`AssignIn`) |
| GET | `/tasks/{task_id}/assignments` | Статусы назначений |
| PATCH | `/tasks/assignments/{assignment_id}` | Проверить/оценить решение (`ReviewIn`) |

### Вакансии — `/api/v1/vacancies`
| Метод | Путь | Роль | Описание |
|---|---|---|---|
| GET | `` | публично | Список открытых вакансий |
| GET | `/mine` | employer | Мои вакансии |
| POST | `` | employer | Создать вакансию (201) |
| PUT | `/{vacancy_id}` | employer | Обновить вакансию |
| POST | `/{vacancy_id}/close` | employer | Закрыть вакансию |
| POST | `/{vacancy_id}/apply` | candidate | Откликнуться (201) |
| GET | `/applications/mine` | candidate | Мои отклики |
| GET | `/{vacancy_id}/applications` | employer | Отклики на вакансию |
| PATCH | `/applications/{application_id}` | employer | Сменить статус отклика |

### Приглашения — `/api/v1/invitations`
| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `` | employer | Создать приглашение (201) |
| GET | `/sent` | employer | Отправленные |
| GET | `/received` | candidate | Полученные |
| GET | `/{invitation_id}` | любая | Детали приглашения |
| GET | `/{invitation_id}/events` | любая | История событий (FSM-аудит) |
| POST | `/{invitation_id}/accept` | candidate | Принять |
| POST | `/{invitation_id}/decline` | candidate | Отклонить |
| POST | `/{invitation_id}/withdraw` | employer | Отозвать |
| PATCH | `/{invitation_id}` | любая | Сменить статус (`InvitationStatusUpdate`) |

Лимиты (`.env`): `INVITATIONS_PER_DAY`, `INVITATION_PAIR_COOLDOWN_DAYS`, `INVITATION_TTL_DAYS`.

### Поиск — `/api/v1/search`
| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `/candidates` | employer | Гибридный поиск кандидатов (`CandidateSearchIn`) → `MatchedCandidateOut[]` |

---

## Администрирование — `/api/v1/admin` (роль `admin`)

### Конвейер заданий
| Метод | Путь | Описание |
|---|---|---|
| GET | `/tasks/generators` | Список генераторов, статус code-exec и Java |
| POST | `/tasks/preview` | Сгенерировать задание целиком (с ключом/тестами) + валидация. Тело: `language` (python/java/sql), `grade` (intern…lead), опционально `generator_id`, `seed`, `query` |
| POST | `/tasks/validate-bank` | Прогнать валидацию по всем генераторам (`seeds` 1–50, `skip_code_exec`) |
| GET | `/tasks/items?status=&language=` | Банк заданий (до 200, со статистикой сложности) |
| PATCH | `/tasks/items/{item_id}` | Сменить статус: `draft` / `active` / `retired` |
| GET | `/stats/generators` | Показы, средние баллы — калибровка сложности |

### Корпус знаний (RAG)
| Метод | Путь | Описание |
|---|---|---|
| GET | `/knowledge/stats` | Статистика корпуса |
| POST | `/knowledge/ingest` | Индексация (`path` внутри `KNOWLEDGE_DIR` или `builtin_only=true`) |

### Черновики через LLM
| Метод | Путь | Описание |
|---|---|---|
| POST | `/tasks/drafts` | Черновики вопросов (`language`, `grade`, `topic`, `count` 1–10). Требуется `LLM_BASE_URL`/`LLM_MODEL`. Создаются со статусом `draft` |

---

## Конфигурация (`.env`)

Ключевые переменные:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SECRET_KEY` | — | **Обязательно сменить** (HS256 JWT) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | Срок жизни токена |
| `CORS_ORIGINS` | localhost | Разрешённые origins |
| `DATABASE_URL` | `postgresql+asyncpg://fsp:fsp@db:5432/fsp` | Строка подключения |
| `CODE_EXEC_ENABLED` | `false` | Выполнение кода кандидатов. **Не песочница** — включать только на изолированном сервере; для Java собирать образ с `WITH_JDK=1` |
| `EMBEDDING_BACKEND` | `hash` | `hash` (без зависимостей) или `fastembed` (нужен `requirements-ml.txt`) |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Модель эмбеддингов |
| `KNOWLEDGE_DIR` | `/data/ru-test-assignments` | Каталог корпуса знаний |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | пусто | OpenAI-совместимый LLM для черновиков |
| `REQUIRE_EMAIL_VERIFICATION` | `false` | В production включить в `true` |
| `MAIL_BACKEND` | `console` | `console` (письма в лог) или `smtp` |
| `WITH_JDK` (docker build arg) | 0 | Включить JDK в образ для Java-заданий |

Полный список — в `.env.example`.

---

## Архитектура (кратко)

```
app/
├── main.py            # FastAPI, CORS, lifespan (фоновый maintenance-цикл)
├── api/v1/            # Роутеры по доменам (auth, candidates, employers, ...)
├── core/              # config, security (JWT), deps, errors (доменные исключения)
├── db/                # session, init_db, seed, patches
├── models/            # SQLAlchemy-модели (user, candidate, employer, vacancy, ...)
├── schemas/           # Pydantic-схемы запросов/ответов
├── services/          # Бизнес-логика (auth, matching, assessment, strength, ...)
├── domain/            # Чистые доменные правила (ranking, trust_rules, grade_policy, invitation_fsm)
├── tasks/             # Конвейер заданий: генераторы, RAG (ingest/chunking/retriever), runners
├── search/            # Гибридный поиск: эмбеддинги + ранжирование
└── integrations/fsp.py  # Интеграция с внешней FSP (mock-режим: FSP_MOCK_MODE=true)
```

Фоновый цикл (раз в 5 минут): истечение приглашений/сессий; раз в сутки — пересчёт силы профилей.
Отключается через `BACKGROUND_JOBS_ENABLED=false`.

Принципы: доменные ошибки возвращаются в едином формате (`DomainError` → JSON с `code` и сообщением),
все ответы строго через Pydantic-схемы, аудит переходов приглашений — через `InvitationEvent`.
