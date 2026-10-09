"""Чистые функции гибридного retrieval: слияние рангов (RRF), разнообразие (MMR), подсказки тем."""
from __future__ import annotations

import math
import re
from typing import Any, Sequence

from app.tasks.types import GRADE_INDEX, ContextPack, GeneratorDef


def rrf(rank_lists: Sequence[Sequence[Any]], k: int = 60) -> list[tuple[Any, float]]:
    """Reciprocal Rank Fusion: объединяет ранжирования (вектор + ключевые слова) без калибровки шкал."""
    scores: dict[Any, float] = {}
    for lst in rank_lists:
        for r, item in enumerate(lst):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + r + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def mmr(cands: list[dict], qvec: Sequence[float], k: int = 6, lam: float = 0.7) -> list[dict]:
    """Maximal Marginal Relevance: релевантность запросу минус сходство с уже выбранным (разнообразие контекста).
    cands: [{"id":..., "vec":[...], "base": float}] — base учитывается как дополнительная релевантность."""
    chosen: list[dict] = []
    pool = list(cands)
    while pool and len(chosen) < k:
        best, best_val = None, -1e9
        for c in pool:
            rel = 0.5 * cosine(c["vec"], qvec) + 0.5 * c.get("base", 0.0)
            div = max((cosine(c["vec"], s["vec"]) for s in chosen), default=0.0)
            val = lam * rel - (1 - lam) * div
            if val > best_val:
                best, best_val = c, val
        chosen.append(best)
        pool.remove(best)
    return chosen


def grade_affinity(chunk_grade: str | None, target: str) -> float:
    if not chunk_grade or chunk_grade not in GRADE_INDEX:
        return 0.5
    d = abs(GRADE_INDEX[chunk_grade] - GRADE_INDEX[target])
    return {0: 1.0, 1: 0.7, 2: 0.35}.get(d, 0.1)


def topic_hints(text: str, generators: Sequence[GeneratorDef]) -> dict[str, float]:
    """Вес темы = сколько ключевых слов генераторов этой темы встретилось в найденном контексте."""
    low = (text or "").lower()
    out: dict[str, float] = {}
    for g in generators:
        hits = sum(len(re.findall(re.escape(k.lower()), low)) for k in g.keywords)
        if hits:
            out[g.topic] = out.get(g.topic, 0.0) + hits
    mx = max(out.values(), default=0.0)
    return {t: v / mx for t, v in out.items()} if mx else {}


def build_context(query: str, chunks: list[dict], generators: Sequence[GeneratorDef]) -> ContextPack:
    text = "\n".join(c["text"] for c in chunks)
    sources = []
    for c in chunks:
        label = c.get("label")
        if label and label not in sources:
            sources.append(label)
    return ContextPack(query=query, text=text, sources=sources, topic_hints=topic_hints(text, generators), chunks=chunks)
