"""Проверка ответов кандидата. Чистая логика (без БД); тяжёлые проверки (SQL/код) синхронные —
вызывать из потока (run_in_threadpool)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.tasks.runners.code_runner import java_available, run_java_function, run_python_function
from app.tasks.runners.sql_runner import SqlRunError, compare_results, run_select
from app.tasks.types import Kind


@dataclass
class GradeResult:
    score: float | None            # 0..1; None — задание не оценено (например, раннер выключен) и не входит в итог
    details: dict[str, Any] = field(default_factory=dict)
    needs_review: bool = False


def _norm(v: Any) -> str:
    return str(v if v is not None else "").strip().lower()


def score_rubric(answer: str, rubric: list[dict]) -> tuple[float, list[dict]]:
    text = (answer or "").lower()
    total = sum(p.get("weight", 1.0) for p in rubric) or 1.0
    got, detail = 0.0, []
    for p in rubric:
        hits = sum(1 for kw in p["keywords"] if kw.lower() in text)
        frac = min(1.0, hits / max(1, p.get("min_hits", 1)))
        got += frac * p.get("weight", 1.0)
        detail.append({"point": p["point"], "covered": frac >= 1.0})
    score = got / total
    if len(text) < 200:               # слишком короткий ответ не может получить высокую оценку
        score = min(score, 0.3)
    words = re.findall(r"\w+", text)
    if words and len(set(words)) / len(words) < 0.35:   # грубая защита от набивки ключевыми словами
        score = min(score, 0.4)
    return round(score, 4), detail


def grade_answer(kind: str, language: str, public: dict, private: dict, answer: Any, *,
                 code_exec_enabled: bool = False) -> GradeResult:
    value = answer.get("value") if isinstance(answer, dict) else answer
    if value in (None, "", []):
        return GradeResult(0.0, {"error": "NO_ANSWER"})

    if kind in (Kind.QUIZ_SINGLE, Kind.PREDICT):
        return GradeResult(1.0 if _norm(value) == _norm(private.get("correct")) else 0.0)

    if kind == Kind.QUIZ_MULTI:
        correct = {_norm(c) for c in private.get("correct", [])}
        given = {_norm(v) for v in (value if isinstance(value, list) else [value])}
        if not correct:
            return GradeResult(0.0)
        return GradeResult(max(0.0, (len(correct & given) - len(given - correct)) / len(correct)))

    if kind == Kind.SQL_QUERY:
        passed, errors = 0, []
        for ds, expected in zip(private["datasets"], private["expected"]):
            try:
                res = run_select(ds, str(value))
                ok = compare_results(expected, res.rows, ordered=private["ordered"])
            except SqlRunError as e:
                errors.append(e.code)
                ok = False
            passed += int(ok)
        n = len(private["datasets"])
        d: dict[str, Any] = {"passed": passed, "total": n}
        if errors:
            d["error"] = errors[0]
        return GradeResult(passed / n, d)

    if kind == Kind.CODE_FUNCTION:
        if not code_exec_enabled or (language == "java" and not java_available()):
            return GradeResult(None, {"error": "CODE_EXEC_DISABLED"})
        tests = private["tests"]
        if language == "python":
            r = run_python_function(str(value), tests)
        else:
            r = run_java_function(str(value), tests, result_format=private.get("result_format", "scalar"))
        d = {"passed": r.passed, "total": r.total}
        if r.error:
            d["error"], d["message"] = r.error, r.message
        # Частичный балл — квадрат доли пройденных тестов: неверное решение не получает «зачёт» только за
        # тривиальные случаи (n=0, пустой список), а почти верное всё же оценивается заметно выше нуля.
        return GradeResult(r.ratio if r.ratio == 1.0 else r.ratio ** 2, d)

    if kind == Kind.APPROACH:
        score, detail = score_rubric(str(value), private["rubric"])
        return GradeResult(score, {"rubric": detail}, needs_review=True)

    return GradeResult(0.0, {"error": "UNKNOWN_KIND"})
