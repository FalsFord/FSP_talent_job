"""Конвейер: URL -> клон -> анализаторы -> итоговая оценка 0..1 (та же шкала, что auto_score в основном бэкенде)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from . import gitutil
from .analyzers import history, quality, rubric, secrets_scan, structure, tests_check
from .analyzers.common import Ctx, Result, finding
from .config import Settings
from .security import validate_ref, validate_repo_url

log = logging.getLogger("git_eval")
VERSION = "1"

DEFAULT_WEIGHTS = {"structure": 0.15, "history": 0.15, "quality": 0.25, "tests": 0.15, "rubric": 0.25, "secrets": 0.05}
ANALYZERS = [("structure", structure.analyze), ("history", history.analyze), ("quality", quality.analyze),
             ("tests", tests_check.analyze), ("secrets", secrets_scan.analyze), ("rubric", rubric.analyze)]


class EmptyRepo(RuntimeError):
    pass


def _verdict(score: float) -> str:
    return "strong" if score >= 0.75 else "acceptable" if score >= 0.5 else "weak"


def evaluate(req: dict, workdir: Path, s: Settings) -> dict:
    started = time.monotonic()
    url = validate_repo_url(req["repo_url"], s)
    ref = validate_ref(req.get("ref"))
    dest = workdir / "repo"
    head = gitutil.clone(url, ref, dest, s)
    files = gitutil.tracked_files(dest, s)
    if not files:
        raise EmptyRepo("Репозиторий пуст")

    ctx = Ctx(root=dest, files=files, language=req.get("language"), rubric=req.get("rubric") or [],
              expected_author=req.get("expected_author"), settings=s)
    langs = ctx.languages()
    if ctx.language is None and langs:
        ctx.language = langs.most_common(1)[0][0]

    results: list[Result] = []
    for name, fn in ANALYZERS:
        try:
            results.append(fn(ctx))
        except Exception:                       # падение одного анализатора не должно ронять всю оценку
            log.exception("analyzer %s failed", name)
            results.append(Result(name, None, {}, [finding("warn", "analyzer_failed", f"Анализатор «{name}» не отработал")]))

    weights = {**DEFAULT_WEIGHTS, **(req.get("weights") or {})}
    used = []
    for r in results:
        w = float(weights.get(r.name, 0))
        if r.name == "quality" and r.metrics.get("limited"):
            w *= 0.4                              # для не-Python языков доверяем качеству меньше
        if r.score is not None and w > 0:
            used.append((r, w))
    total_w = sum(w for _, w in used)
    wmap = {r.name: w / total_w for r, w in used} if total_w else {}      # нормированные веса — что реально вошло в оценку
    score = sum(r.score * w for r, w in used) / total_w if total_w else 0.0

    flags: list[str] = []
    if not ctx.source_files:
        flags.append("no_source_code")
        score = min(score, 0.2)
    for r in results:
        flags += r.metrics.get("flags", [])
        if r.name == "secrets" and r.metrics.get("hits"):
            flags.append("secrets_committed")
    score = round(score, 3)

    sev = {"bad": 0, "warn": 1, "info": 2}
    all_f = sorted((x for r in results for x in r.findings), key=lambda x: sev.get(x["severity"], 3))
    return {
        "version": VERSION,
        "score": score,
        "verdict": _verdict(score),
        "flags": sorted(set(flags)),
        "summary": [x["text"] for x in all_f[:6]],
        "breakdown": {r.name: {"score": r.score, "weight": round(wmap.get(r.name, 0.0), 3),
                               "metrics": {k: v for k, v in r.metrics.items() if k != "flags"}, "findings": r.findings}
                      for r in results},
        "repo": {"url": url, "ref": ref, "head_sha": head, "files": len(files),
                 "languages": dict(langs.most_common(5))},
        "duration_s": round(time.monotonic() - started, 2),
    }
