"""Тесты: есть ли они, какова доля тестового кода, есть ли в них проверки (assert). Опционально — реальный прогон."""
from __future__ import annotations

import re

from . import sandbox
from .common import Ctx, Result, clamp, finding

_ASSERT = re.compile(r"\bassert\b|assert[A-Z]\w*\(|\bexpect\(|\.should\b|assert_eq!|\bt\.(Error|Fatal)f?\(")
_TEST_FN = re.compile(r"\bdef test_\w+|@Test\b|\bfunc Test\w+|\b(it|test)\(\s*['\"]")


def analyze(ctx: Ctx) -> Result:
    tests = ctx.test_files
    f: list[dict] = []
    if not tests:
        return Result("tests", 0.0, {"test_files": 0},
                      [finding("bad", "no_tests", "Тестов нет")])

    test_loc = sum(ctx.loc(x) for x in tests)
    src_loc = sum(ctx.loc(x) for x in ctx.source_files)
    n_fn = sum(len(_TEST_FN.findall(ctx.text(x))) for x in tests)
    n_assert = sum(len(_ASSERT.findall(ctx.text(x))) for x in tests)
    ratio = test_loc / max(src_loc, 1)

    score = max(0.3, clamp(ratio / 0.3))
    if n_fn and n_assert / n_fn < 0.8:
        score *= 0.6
        f.append(finding("warn", "weak_asserts", "В тестах мало проверок: тесты могут ничего не утверждать"))
    if ratio < 0.1:
        f.append(finding("warn", "low_test_ratio", f"Тестового кода мало: {round(ratio * 100)}% от объёма исходного"))
    metrics = {"test_files": len(tests), "test_functions": n_fn, "asserts": n_assert, "test_to_src_loc": round(ratio, 2)}

    s = ctx.settings
    if s.sandbox_enabled and (ctx.language in (None, "python")):
        run = sandbox.run_pytest(str(ctx.root), s)
        metrics["sandbox"] = run
        if run and run["total"] > 0:
            rate = run["passed"] / run["total"]
            score = 0.5 * score + 0.5 * rate
            f.append(finding("info" if rate >= 0.8 else "warn", "tests_run",
                             f"Прогон тестов: {run['passed']} из {run['total']} прошли"))
        else:
            f.append(finding("warn", "tests_not_run", "Тесты не удалось запустить в песочнице (нет зависимостей или ошибка запуска)"))
    return Result("tests", round(clamp(score), 3), metrics, f)
