"""Соответствие заданию: те же пункты рубрики {point, keywords, min_hits, weight}, что и в основном бэкенде.

Ищем ключевые слова в README и исходниках. Это дешёвая эвристика: слова легко вставить в комментарий,
поэтому оценку по рубрике стоит дополнять ревью человека или LLM (см. README, раздел «Что дальше»).
"""
from __future__ import annotations

from .common import Ctx, Result, finding, lang_of

CORPUS_LIMIT = 2_000_000


def analyze(ctx: Ctx) -> Result:
    if not ctx.rubric:
        return Result("rubric", None, {}, [])
    chunks: list[str] = []
    size = 0
    for rel in ctx.files:
        if not (lang_of(rel) or rel.lower().endswith((".md", ".txt", ".rst", ".yml", ".yaml", ".toml", ".json"))):
            continue
        t = ctx.text(rel).lower()
        size += len(t)
        if size > CORPUS_LIMIT:
            break
        chunks.append(t)
    corpus = "\n".join(chunks)

    total_w = got_w = 0.0
    f: list[dict] = []
    detail = []
    for p in ctx.rubric:
        kws = [k.lower() for k in p.get("keywords", []) if k]
        need = max(1, int(p.get("min_hits", 1)))
        w = float(p.get("weight", 1.0))
        found = [k for k in kws if k in corpus]
        ok = len(found) >= need
        total_w += w
        got_w += w if ok else 0
        detail.append({"point": p["point"], "ok": ok, "found": found})
        if not ok:
            f.append(finding("warn", "rubric_miss", f"Не найдено подтверждения пункта: «{p['point']}»"))
    score = got_w / total_w if total_w else 0.0
    return Result("rubric", round(score, 3), {"points": detail}, f)
