"""Базовые типы конвейера заданий. Модуль не зависит от FastAPI/SQLAlchemy."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

LANGUAGES = ("python", "java", "sql")
GRADES = ("intern", "junior", "middle", "senior", "lead")
GRADE_INDEX = {g: i for i, g in enumerate(GRADES)}


class Kind:
    QUIZ_SINGLE = "quiz_single"      # один правильный ответ из вариантов
    QUIZ_MULTI = "quiz_multi"        # несколько правильных
    PREDICT = "predict_output"       # «что выведет код» (варианты, ответ вычислен генератором)
    SQL_QUERY = "sql_query"          # кандидат пишет SELECT, проверка на скрытых наборах данных
    CODE_FUNCTION = "code_function"  # кандидат пишет функцию, проверка скрытыми тестами (песочница)
    APPROACH = "approach"            # «опишите подход», оценка по рубрике (+ ручная проверка)

    CHOICE = (QUIZ_SINGLE, QUIZ_MULTI, PREDICT)
    EXECUTABLE = (SQL_QUERY, CODE_FUNCTION)


@dataclass
class TaskSpec:
    """Конкретный экземпляр задания, готовый к выдаче кандидату.

    public  — то, что видит кандидат (варианты, схема БД, заготовка кода).
    private — ключ ответа/тесты. Никогда не отдаётся через API кандидату.
    """

    generator_id: str
    kind: str
    language: str
    grade: str
    topic: str
    seed: int
    statement: str
    public: dict[str, Any]
    private: dict[str, Any]
    difficulty: float = 0.0           # параметр сложности b (условные единицы, калибруется)
    weight: float = 1.0
    time_limit_s: int = 120
    manual_review: bool = False
    sources: list[str] = field(default_factory=list)  # атрибуция: из каких материалов взят контекст

    def fingerprint(self) -> str:
        """Отпечаток параметров экземпляра: разные сиды → разные отпечатки."""
        raw = json.dumps(
            {"g": self.generator_id, "s": self.statement, "p": self.public}, sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "language": self.language,
            "topic": self.topic,
            "statement": self.statement,
            "public": self.public,
            "time_limit_s": self.time_limit_s,
        }


@dataclass
class GeneratorDef:
    """Описание генератора в реестре."""

    id: str
    language: str
    kind: str
    topic: str
    grades: tuple[str, ...]
    difficulty: float
    keywords: tuple[str, ...]
    build: Any  # callable(rng, ctx, grade, seed) -> TaskSpec
    needs_code_exec: bool = False
    time_limit_s: int = 180
    weight: float = 1.0


@dataclass
class ContextPack:
    """Результат retrieval-шага: что система «знает» перед генерацией задания."""

    query: str = ""
    text: str = ""                      # склеенный текст найденных чанков (для выбора темы/архетипа)
    sources: list[str] = field(default_factory=list)
    topic_hints: dict[str, float] = field(default_factory=dict)  # topic -> вес
    chunks: list[dict[str, Any]] = field(default_factory=list)
