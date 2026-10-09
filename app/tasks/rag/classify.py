"""Эвристическая разметка документов корпуса: язык, грейд, темы, компания. Без внешних зависимостей."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LANG_PATTERNS = {
    "python": [r"\bpython\b", r"\bdjango\b", r"\bflask\b", r"\bfastapi\b", r"\bpytest\b"],
    "java": [r"\bjava\b(?!script)", r"\bspring\b", r"\bkotlin\b", r"\bjvm\b", r"\bmaven\b", r"\bgradle\b"],
    "sql": [r"\bsql\b", r"\bpostgres(?:ql)?\b", r"\bmysql\b", r"\bselect\b.+\bfrom\b", r"\bjoin\b", r"\bgroup by\b"],
}
GRADE_PATTERNS = [
    ("lead", r"\b(lead|руководител|head of|тимлид|team lead)\b"),
    ("senior", r"\bsenior\b|\bсеньор"),
    ("middle", r"\bmiddle\b|\bмиддл"),
    ("junior", r"\bjunior\b|\bджуниор|junior\+"),
    ("intern", r"\bintern\b|стаж[её]р|стажировк|trainee"),
]
TOPIC_PATTERNS = {
    "sql_joins_aggregation": r"\bjoin\b|group by|агрегат|having",
    "sql_window": r"\bwindow\b|row_number|over\s*\(|оконн",
    "sql_schema": r"схем[аыу] бд|нормализац|create table|миграц",
    "rest_api": r"\brest\b|\bapi\b|эндпоинт|endpoint|crud",
    "concurrency": r"потокобезоп|многопоточн|thread|concurren|асинхрон|asyncio",
    "caching": r"\bcache\b|кэш|кеш|\bttl\b|\blru\b",
    "rate_limit": r"rate limit|антибан|ограничени[ея] частот|throttl",
    "large_data": r"большо[йм] файл|гигабайт|терабайт|потоков(ая|ое) обработк|ограниченн\w+ памят",
    "collections_algorithms": r"алгоритм|сортиров|коллекц|массив|структур[аы] данных|сложност",
    "testing": r"\bтест|pytest|junit|unit-тест|покрыти",
    "docker_devops": r"\bdocker\b|compose|ci/cd|kubernetes",
    "oop_design": r"\bооп\b|паттерн|solid|наследован|интерфейс|архитектур",
}


@dataclass
class DocMeta:
    languages: list[str] = field(default_factory=list)
    grade_hint: str | None = None
    topics: list[str] = field(default_factory=list)
    company: str | None = None


def company_from_path(rel_path: str) -> str | None:
    parts = [p for p in re.split(r"[\\/]", rel_path) if p]
    if len(parts) >= 3 and parts[0] == "backend" and parts[1] in ("python", "java"):
        return parts[2]
    if len(parts) >= 2:
        return parts[1] if parts[0] in ("java", "sql", "analytics", "qa", "backend", "devops", "other") else None
    return None


def classify(rel_path: str, title: str, text: str) -> DocMeta:
    low_path = rel_path.lower().replace("\\", "/")
    blob = f"{title}\n{text}".lower()
    langs: list[str] = []
    for lang, pats in LANG_PATTERNS.items():
        path_hit = f"/{lang}/" in f"/{low_path}" or low_path.startswith(f"{lang}/")
        text_hits = sum(len(re.findall(p, blob)) for p in pats)
        if path_hit or text_hits >= 2:
            langs.append(lang)
    grade = None
    head = f"{title}\n{blob[:600]}"
    for g, pat in GRADE_PATTERNS:
        if re.search(pat, head):
            grade = g
            break
    if grade is None:  # грубая оценка по объёму/сложности требований
        bullets = len(re.findall(r"^\s*[-*•]\s", text, re.M))
        grade = "junior" if len(text) < 1500 and bullets < 8 else "middle"
    topics = [t for t, pat in TOPIC_PATTERNS.items() if re.search(pat, blob)]
    return DocMeta(languages=langs, grade_hint=grade, topics=topics, company=company_from_path(rel_path))
