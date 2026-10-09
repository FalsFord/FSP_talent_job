"""Автоматическая валидация заданий и всего банка генераторов (метрики качества для документации и CI)."""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Iterable

from app.tasks.rng import sub_seed
from app.tasks.runners.sql_runner import SqlRunError, compare_results, run_select
from app.tasks.types import ContextPack, GeneratorDef, Kind, TaskSpec

_SQL_MUTATIONS = [(" > ", " >= "), (" >= ", " > "), ("DESC", "ASC"), ("ASC", "DESC"), ("COUNT(DISTINCT p.id)", "COUNT(p.id)"),
                  ("NOT EXISTS", "EXISTS"), ("ROW_NUMBER()", "RANK()"), ("rn <=", "rn <"), ("<= ", "< "),
                  ("JOIN", "LEFT JOIN"), ("PARTITION BY", "PARTITION BY 1 +"), ("SUM(", "MAX(")]


@dataclass
class ValidationReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)


def _shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def sql_discrimination(spec: TaskSpec) -> tuple[int, int]:
    """Сколько типовых «ошибочных» вариантов эталонного запроса отличается по результату от эталона:
    показывает, что задание способно отличить неверное решение от верного."""
    ref = spec.private["reference_sql"]
    applicable = killed = 0
    for old, new in _SQL_MUTATIONS:
        if old not in ref:
            continue
        mutated = ref.replace(old, new, 1)
        applicable += 1
        differs = False
        for ds, exp in zip(spec.private["datasets"], spec.private["expected"]):
            try:
                got = run_select(ds, mutated).rows
                if not compare_results(exp, got, ordered=spec.private["ordered"]):
                    differs = True
                    break
            except SqlRunError:
                differs = True
                break
        killed += int(differs)
    return killed, applicable


def validate_spec(spec: TaskSpec, source_texts: Iterable[str] = ()) -> ValidationReport:
    r = ValidationReport()
    if len(spec.statement) < 15:
        r.fail("statement слишком короткий")
    if spec.kind in Kind.CHOICE:
        opts = spec.public.get("options", [])
        if len(opts) < 3 or len(set(opts)) != len(opts):
            r.fail("варианты ответа: нужно ≥3 уникальных")
        correct = spec.private.get("correct")
        if isinstance(correct, list):
            if not set(correct) <= set(opts):
                r.fail("правильные ответы вне списка вариантов")
        elif correct not in opts:
            r.fail("правильный ответ отсутствует среди вариантов")
    elif spec.kind == Kind.SQL_QUERY:
        for i, (ds, exp) in enumerate(zip(spec.private["datasets"], spec.private["expected"])):
            try:
                got = run_select(ds, spec.private["reference_sql"]).rows
            except SqlRunError as e:
                r.fail(f"эталон не выполняется на наборе {i}: {e.code}")
                continue
            if not compare_results(exp, got, ordered=spec.private["ordered"]):
                r.fail(f"эталон не воспроизводит expected на наборе {i}")
        killed, applicable = sql_discrimination(spec)
        if applicable:
            r.metrics["discrimination"] = killed / applicable
            if killed / applicable < 0.5:
                r.warnings.append(f"низкая различающая способность: {killed}/{applicable}")
    elif spec.kind == Kind.CODE_FUNCTION:
        tests = spec.private.get("tests", [])
        if len(tests) < 5:
            r.fail("слишком мало тестов")
        key = "expected" if tests and "expected" in tests[0] else "expected_str"
        if len({repr(t.get(key)) for t in tests}) < 2:
            r.fail("вырожденные тесты: ожидаемый результат одинаков")
    elif spec.kind == Kind.APPROACH:
        if len(spec.private.get("rubric", [])) < 3:
            r.fail("рубрика: нужно ≥3 пункта")
    for text in source_texts:  # защита от дословного копирования внешнего корпуса
        sim = similarity(spec.statement, text)
        r.metrics["max_source_similarity"] = max(r.metrics.get("max_source_similarity", 0.0), sim)
        if sim > 0.35:
            r.fail(f"условие слишком похоже на материал корпуса (sim={sim:.2f})")
    return r


def validate_bank(generators: Iterable[GeneratorDef], seeds: Iterable[int] = range(20),
                  skip_code_exec: bool = False) -> dict[str, dict]:
    """Проверка всех генераторов: доля успешных сборок, размер пространства вариантов, различающая способность."""
    out: dict[str, dict] = {}
    seeds = list(seeds)
    for g in generators:
        if skip_code_exec and g.needs_code_exec:
            continue
        fps, ok, errors, disc, t_total = set(), 0, [], [], 0.0
        for grade in g.grades[:1]:
            for sd in seeds:
                s = sub_seed(sd, g.id)
                t0 = time.perf_counter()
                try:
                    spec = g.build(random.Random(s), ContextPack(), grade, s)
                    rep = validate_spec(spec)
                    t_total += time.perf_counter() - t0
                    if rep.ok:
                        ok += 1
                        fps.add(spec.fingerprint())
                        if "discrimination" in rep.metrics:
                            disc.append(rep.metrics["discrimination"])
                    else:
                        errors += rep.errors
                except Exception as e:  # noqa: BLE001
                    errors.append(repr(e))
        out[g.id] = {
            "built_ok": ok, "attempts": len(seeds), "variant_space": len(fps),
            "mean_discrimination": round(sum(disc) / len(disc), 3) if disc else None,
            "avg_build_ms": round(1000 * t_total / max(1, len(seeds)), 1), "errors": sorted(set(errors))[:3],
        }
    return out
