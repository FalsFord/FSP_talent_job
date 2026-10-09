"""Сила подтверждённого профиля, оценка соответствия потребности, объяснения. Чистые функции."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Iterable

W_SEMANTIC, W_SKILLS, W_KEYWORD, W_GRADE, W_FORMAT = 0.35, 0.30, 0.10, 0.15, 0.10
W_MATCH_IN_RANK, W_STRENGTH_IN_RANK = 0.6, 0.4
SKILL_WEIGHT = {"verified": 1.0, "declared": 0.5, "stale": 0.7}


def fsp_score(achievements: Iterable[dict], today: date | None = None) -> float:
    """0..1. Участие даёт базовый вклад, призовое место — бонус, давность — затухание (полураспад 2 года).
    Нет истории → 0.0: бонуса нет, штрафа тоже (ТЗ: корректная обработка отсутствия истории ФСП)."""
    today = today or date.today()
    total = 0.0
    for a in achievements:
        base = 0.35
        place = a.get("place")
        if isinstance(place, int):
            base += {1: 0.5, 2: 0.4, 3: 0.3}.get(place, 0.15 if place <= 10 else 0.0)
        d = a.get("date")
        if isinstance(d, datetime):
            d = d.date()
        age_years = max(0.0, (today - d).days / 365.0) if isinstance(d, date) else 1.0
        total += base * math.pow(0.5, age_years / 2.0)
    return min(1.0, total)


def strength_score(*, test_ratio: float | None, fsp: float, task_ratio: float | None,
                   freshness: float) -> float:
    """0..100. 0.60 результат тестирования + 0.25 ФСП + 0.15 регулярные задания, умноженное на «свежесть»."""
    t = test_ratio if test_ratio is not None else 0.0
    k = task_ratio if task_ratio is not None else 0.0
    return round(100.0 * freshness * (0.60 * t + 0.25 * fsp + 0.15 * k), 2)


def skills_overlap(required: list[str], candidate: dict[str, str]) -> tuple[float, list[str], list[str]]:
    """required — навыки потребности; candidate: {skill_lower: status}. Возвращает (доля, совпавшие, недостающие)."""
    if not required:
        return 0.0, [], []
    got, miss, acc = [], [], 0.0
    for s in required:
        st = candidate.get(s.lower())
        if st:
            acc += SKILL_WEIGHT.get(st, 0.5)
            got.append(s)
        else:
            miss.append(s)
    return acc / len(required), got, miss


def grade_fit(need_levels: list[int], cand_level: int | None) -> float:
    if not need_levels or cand_level is None:
        return 0.5
    d = min(abs(cand_level - n) for n in need_levels)
    return {0: 1.0, 1: 0.5}.get(d, 0.0)


def match_score(*, semantic: float, skills: float, keyword: float, grade: float, fmt: float) -> float:
    sem = max(0.0, min(1.0, semantic))
    return W_SEMANTIC * sem + W_SKILLS * skills + W_KEYWORD * keyword + W_GRADE * grade + W_FORMAT * fmt


def rank_score(match: float, strength_0_100: float) -> float:
    return W_MATCH_IN_RANK * match + W_STRENGTH_IN_RANK * (strength_0_100 / 100.0)


def build_reasons(*, semantic: float, skills: float, matched: list[str], missing: list[str], verified: list[str],
                  grade_fit_v: float, fmt_ok: bool, fsp: float, fsp_count: int, status: str) -> list[dict]:
    r: list[dict] = []
    if semantic >= 0.35:
        r.append({"code": "SEMANTIC", "weight": round(W_SEMANTIC * semantic, 3),
                  "text": "Профиль по смыслу близок к описанию потребности"})
    if matched:
        v = [s for s in matched if s.lower() in {x.lower() for x in verified}]
        extra = f"; подтверждено тестом: {', '.join(v)}" if v else ""
        r.append({"code": "SKILLS", "weight": round(W_SKILLS * skills, 3),
                  "text": f"Совпало {len(matched)} из {len(matched) + len(missing)} технологий{extra}"})
    if grade_fit_v >= 1.0:
        r.append({"code": "GRADE", "weight": W_GRADE, "text": "Подтверждённый грейд соответствует запросу"})
    elif grade_fit_v >= 0.5:
        r.append({"code": "GRADE_NEAR", "weight": round(W_GRADE * grade_fit_v, 3), "text": "Грейд на соседнем уровне"})
    if fmt_ok:
        r.append({"code": "FORMAT", "weight": W_FORMAT, "text": "Формат работы и город подходят"})
    if fsp_count:
        r.append({"code": "FSP", "weight": round(0.25 * fsp * 0.4, 3),
                  "text": f"Подтверждённые достижения ФСП: {fsp_count}"})
    if status == "stale":
        r.append({"code": "STALE", "weight": 0.0, "text": "Подтверждение грейда устарело — рекомендуется повторная проверка"})
    return r
