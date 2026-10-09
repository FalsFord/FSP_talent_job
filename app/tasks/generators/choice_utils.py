"""Помощники для заданий с выбором: варианты строятся из правильного ответа и «мутантов» кода."""
from __future__ import annotations

import contextlib
import io
import random


def run_trusted(code: str) -> str:
    """Выполняет сгенерированный НАМИ сниппет (только целочисленные параметры из шаблона) и возвращает stdout.
    Код кандидата здесь никогда не выполняется."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<template>", "exec"), {"__name__": "__template__"})
    except Exception as e:  # ожидаемый результат тоже может быть исключением (ловушка)
        return f"{type(e).__name__}"
    return buf.getvalue().strip()


def build_options(rng: random.Random, correct: str, distractors: list[str], n: int = 4) -> tuple[list[str], str]:
    uniq: list[str] = []
    for d in distractors:
        if d != correct and d not in uniq and d.strip():
            uniq.append(d)
    rng.shuffle(uniq)
    options = [correct] + uniq[: n - 1]
    rng.shuffle(options)
    return options, correct


def numeric_fillers(rng: random.Random, correct: str) -> list[str]:
    """Правдоподобные числовые дистракторы, если мутантов не хватило."""
    out: list[str] = []
    try:
        v = int(correct)
        for d in (-2, -1, 1, 2, 3, 10):
            out.append(str(v + d))
    except ValueError:
        pass
    rng.shuffle(out)
    return out
