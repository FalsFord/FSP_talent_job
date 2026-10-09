import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.assessment import AssessmentQuestion, QuestionType
from app.models.candidate import CandidateProfile, Category
from app.models.employer import Company, EmployerProfile
from app.models.fsp import FSPAchievement, FSPParticipantLink
from app.models.reference import Grade, Skill, Specialization
from app.models.user import User, UserRole
from app.search.embedding import build_candidate_search_text, embed_text
from app.domain import grade_policy as gp
from app.models.tasks import TaskItem
from app.services.category_service import ensure_category
from app.services.knowledge_service import ingest_builtin
from app.services.strength_service import recompute_strength
from app.tasks.quiz_bank import QUIZ_ITEMS


SPECIALIZATIONS = [
    ("backend", "Backend-разработка", 1),
    ("frontend", "Frontend-разработка", 2),
    ("devops", "DevOps", 3),
    ("qa", "QA / тестирование", 4),
    ("data", "Data Engineering", 5),
]

GRADES = [
    ("intern", "Intern", 0, 1),
    ("junior", "Junior", 1, 2),
    ("middle", "Middle", 2, 3),
    ("senior", "Senior", 3, 4),
    ("lead", "Lead", 4, 5),
]

SKILLS = [
    "python", "fastapi", "postgresql", "docker", "react", "typescript", "javascript",
    "kubernetes", "linux", "sql", "redis", "git", "rest", "api", "pytest", "java",
]

QUESTIONS = [
    {
        "prompt": "Какой HTTP-метод идempotent для обновления ресурса целиком?",
        "options": {"choices": ["POST", "PUT", "PATCH", "CONNECT"]},
        "correct": {"value": "PUT"},
        "tags": ["rest", "api"],
        "difficulty": 2,
    },
    {
        "prompt": "Что делает dependency injection в FastAPI?",
        "options": {
            "choices": [
                "Компилирует Python в C",
                "Предоставляет переиспользуемые зависимости для endpoints",
                "Шифрует JWT",
                "Создаёт миграции Alembic",
            ]
        },
        "correct": {"value": "Предоставляет переиспользуемые зависимости для endpoints"},
        "tags": ["fastapi", "python"],
        "difficulty": 2,
    },
    {
        "prompt": "Какой тип индекса в PostgreSQL ускоряет similarity search с pgvector?",
        "options": {"choices": ["B-tree", "GIN", "HNSW", "Hash"]},
        "correct": {"value": "HNSW"},
        "tags": ["postgresql", "sql"],
        "difficulty": 3,
    },
    {
        "prompt": "Выберите верное утверждение про async/await в Python",
        "options": {
            "choices": [
                "await можно использовать в любой функции",
                "async def создаёт корутину",
                "async блокирует GIL навсегда",
                "await выполняет CPU-bound задачи быстрее",
            ]
        },
        "correct": {"value": "async def создаёт корутину"},
        "tags": ["python"],
        "difficulty": 1,
    },
    {
        "prompt": "Dockerfile: зачем multi-stage build?",
        "options": {
            "choices": [
                "Уменьшить размер финального образа",
                "Ускорить DNS",
                "Обязательное требование Docker Hub",
                "Заменить docker-compose",
            ]
        },
        "correct": {"value": "Уменьшить размер финального образа"},
        "tags": ["docker"],
        "difficulty": 2,
    },
    {
        "prompt": "REST API: код ответа при успешном создании ресурса",
        "options": {"choices": ["200", "201", "204", "301"]},
        "correct": {"value": "201"},
        "tags": ["rest"],
        "difficulty": 1,
    },
]


async def _seed_base(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)

    specs = {}
    for code, name, order in SPECIALIZATIONS:
        s = Specialization(code=code, name=name, sort_order=order)
        db.add(s)
        specs[code] = s
    await db.flush()

    grades = {}
    for code, name, level, order in GRADES:
        g = Grade(code=code, name=name, level=level, sort_order=order)
        db.add(g)
        grades[code] = g
    await db.flush()

    skill_objs = {}
    for name in SKILLS:
        sk = Skill(name=name, slug=name.lower().replace(" ", "-"))
        db.add(sk)
        skill_objs[name] = sk
    await db.flush()

    backend_middle = await ensure_category(db, specs["backend"].id, grades["middle"].id)

    for q in QUESTIONS:
        db.add(
            AssessmentQuestion(
                specialization_id=specs["backend"].id,
                grade_id=grades["middle"].id,
                question_type=QuestionType.single_choice,
                difficulty=q["difficulty"],
                prompt=q["prompt"],
                options=q["options"],
                correct_answer=q["correct"],
                tags=q["tags"],
            )
        )

    company = Company(
        name="ТехноФСП",
        description="Продуктовая команда платформы подбора ИТ-специалистов",
        website="https://example.com",
        industry="IT",
        trust_score=82.0,
    )
    db.add(company)
    await db.flush()

    employer_user = User(
        email="employer@demo.local",
        password_hash=hash_password("demo1234"),
        role=UserRole.employer,
        email_verified=True,
    )
    db.add(employer_user)
    await db.flush()
    db.add(EmployerProfile(user_id=employer_user.id, company_id=company.id, position="Tech Lead"))

    candidates_data = [
        ("candidate@demo.local", "Алексей", "Петров", "Python Developer, FastAPI, PostgreSQL", ["python", "fastapi", "postgresql", "docker"], "middle", True),
        ("maria@demo.local", "Мария", "Иванова", "Backend-разработчик REST API", ["python", "rest", "api", "sql"], "middle", False),
        ("ivan@demo.local", "Иван", "Сидоров", "Junior Frontend React", ["react", "typescript", "javascript"], "junior", False),
    ]

    for email, fn, ln, headline, cskills, grade_code, with_fsp in candidates_data:
        user = User(
            email=email,
            password_hash=hash_password("demo1234"),
            role=UserRole.candidate,
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        grade = grades[grade_code]
        spec_id = specs["frontend"].id if "react" in headline.lower() else specs["backend"].id
        cat = await ensure_category(db, spec_id, grade.id)
        spec_name = specs["frontend"].name if spec_id == specs["frontend"].id else specs["backend"].name
        profile = CandidateProfile(
            user_id=user.id,
            first_name=fn,
            last_name=ln,
            headline=headline,
            city="Москва",
            remote_ok=True,
            phone="+7-900-000-00-01",
            about=f"Специалист: {headline}. Опыт коммерческой разработки.",
            category_id=cat.id,
            declared_grade_id=grade.id,
            confirmed_grade_id=grade.id,
            specialization_id=cat.specialization_id,
            profile_strength=0.0,
            onboarding_completed=True,
            privacy={"show_contacts_after_accept": True},
            grade_confirmed_at=now,
            grade_valid_until=now + timedelta(days=gp.VALIDITY_DAYS),
            grade_last_changed_at=now - timedelta(days=100),
            last_test_ratio=0.62 + 0.05 * grade.level,
            languages=["python", "sql"],
        )
        db.add(profile)
        await db.flush()

        from app.models.candidate import CandidateSkill, SkillSource, SkillStatus

        for sn in cskills:
            if sn in skill_objs:
                db.add(
                    CandidateSkill(
                        candidate_id=profile.id,
                        skill_id=skill_objs[sn].id,
                        source=SkillSource.self_declared,
                        status=SkillStatus.claimed,
                    )
                )

        search_text = build_candidate_search_text(
            profile, cskills, grade.name, specs["backend"].name if cat.id != backend_middle.id else specs["backend"].name
        )
        profile.search_text = search_text
        profile.embedding = embed_text(search_text)

        if with_fsp:
            link = FSPParticipantLink(candidate_id=profile.id, external_id="FSP-2024-00142")
            db.add(link)
            await db.flush()
            db.add(
                FSPAchievement(
                    link_id=link.id,
                    title="Призёр отборочного этапа",
                    event_name="Чемпионат ФСП по backend",
                    event_date=date(2024, 11, 15),
                    rank=2,
                    description="Командная задача на проектирование API",
                )
            )

    await db.flush()
    for c in (await db.execute(select(CandidateProfile))).scalars().all():
        await recompute_strength(db, c, now)
    admin = User(
        email="admin@demo.local",
        password_hash=hash_password("demo1234"),
        role=UserRole.admin,
        email_verified=True,
    )
    db.add(admin)
    await db.commit()
    print("Seed completed")


async def seed_task_bank(db: AsyncSession) -> int:
    """Авторский банк вопросов → task_items (идемпотентно по ext_id)."""
    have = set((await db.execute(select(TaskItem.ext_id).where(TaskItem.ext_id.is_not(None)))).scalars().all())
    n = 0
    for it in QUIZ_ITEMS:
        if it["id"] in have:
            continue
        db.add(TaskItem(ext_id=it["id"], kind="quiz_multi" if isinstance(it["correct"], list) else "quiz_single",
                        language=it["language"], grade=it["grade"], topic=it["topic"], statement=it["statement"],
                        options=it["options"], correct=it["correct"], explanation=it["explanation"],
                        difficulty=it["difficulty"], status="active", origin="authored"))
        n += 1
    await db.commit()
    return n


async def backfill_candidates(db: AsyncSession) -> int:
    """Для кандидатов, прошедших категоризацию прежней версией, задаём срок подтверждения и базовый результат
    (консервативно: проходной порог), чтобы они корректно ранжировались; затем пересчитываем силу профиля."""
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(CandidateProfile).where(CandidateProfile.confirmed_grade_id.is_not(None),
                                                            CandidateProfile.grade_valid_until.is_(None)))).scalars().all()
    for c in rows:
        c.grade_confirmed_at = c.grade_confirmed_at or c.grade_last_changed_at or now
        c.grade_valid_until = c.grade_confirmed_at + timedelta(days=gp.VALIDITY_DAYS)
        c.last_test_ratio = c.last_test_ratio if c.last_test_ratio is not None else gp.PASS_RATIO
        await recompute_strength(db, c, now)
    await db.commit()
    return len(rows)


async def seed() -> None:
    async with SessionLocal() as db:
        if (await db.execute(select(User).limit(1))).scalar_one_or_none():
            print("Base seed skipped: data exists")
        else:
            await _seed_base(db)
    async with SessionLocal() as db:
        print("Task bank items added:", await seed_task_bank(db))
        print("Builtin knowledge:", await ingest_builtin(db))
        print("Candidates backfilled:", await backfill_candidates(db))


if __name__ == "__main__":
    asyncio.run(seed())
