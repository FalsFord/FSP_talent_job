"""Сборка теста: из генераторов и банка пунктов выбирается набор заданий по грейду и языкам кандидата.

Структура теста фиксирована (квоты по типам заданий), содержание варьируется по seed — так результаты
сопоставимы между кандидатами, а повторное прохождение даёт другие задания."""
from __future__ import annotations

import random
from typing import Any

from app.tasks.generators import eligible
from app.tasks.rng import rng_for, sub_seed
from app.tasks.types import ContextPack, GeneratorDef, Kind, TaskSpec


def _sanity(spec: TaskSpec) -> None:
    """Дешёвая проверка перед выдачей (полная валидация — app/tasks/validation.py): вырожденные задания не выдаём."""
    if spec.kind in Kind.CHOICE and len(set(spec.public.get("options", []))) < 3:
        raise ValueError("not enough distinct options")
    if spec.kind == Kind.CODE_FUNCTION:
        tests = spec.private.get("tests", [])
        key = "expected" if tests and "expected" in tests[0] else "expected_str"
        if len(tests) < 5 or len({repr(t.get(key)) for t in tests}) < 3:
            raise ValueError("degenerate tests")


def quotas(n: int, grade: str, purpose: str) -> dict[str, int]:
    appr = 1 if (grade in ("middle", "senior", "lead") and n >= 10 and purpose != "micro") else 0
    # Доля генерируемых заданий (SQL/код/«что выведет») намеренно выше доли статических вопросов банка:
    # статические вопросы повторяются между кандидатами и потому уязвимы к обмену ответами (см. app/tasks/simulation.py).
    ex = round(0.40 * n) if purpose != "micro" else round(0.30 * n)
    pred = round(0.30 * n)
    quiz = max(0, n - ex - pred - appr)
    return {"exec": ex, "predict": pred, "quiz": quiz, "approach": appr}


def language_weights(languages: list[str]) -> dict[str, float]:
    langs = list(dict.fromkeys(languages))
    if len(langs) == 1:
        return {langs[0]: 1.0}
    w = {langs[0]: 0.5}
    rest = 0.5 / (len(langs) - 1)
    for l in langs[1:]:
        w[l] = rest
    return w


def _quiz_spec(item: dict, seed: int, grade: str) -> TaskSpec:
    rng = rng_for(seed, "quiz", item["id"])
    opts = list(item["options"])
    rng.shuffle(opts)
    multi = isinstance(item["correct"], list)
    return TaskSpec(
        generator_id=f"item:{item['id']}", kind=Kind.QUIZ_MULTI if multi else Kind.QUIZ_SINGLE,
        language=item["language"], grade=grade, topic=item.get("topic", "general"), seed=seed,
        statement=item["statement"], public={"options": opts}, private={"correct": item["correct"],
                                                                          "explanation": item.get("explanation", "")},
        difficulty=item.get("difficulty", 0.0), time_limit_s=90,
    )


def compose_test(*, seed: int, grade: str, languages: list[str], n_items: int, purpose: str,
                 contexts: dict[str, ContextPack], quiz_pool: list[dict], code_exec: bool, java_ok: bool,
                 recent_generators: set[str] | None = None) -> list[TaskSpec]:
    recent = recent_generators or set()
    rng = rng_for(seed, "compose", grade)
    weights = language_weights(languages)
    q = quotas(n_items, grade, purpose)

    def ctx_for(lang: str) -> ContextPack:
        return contexts.get(lang) or ContextPack()

    def rank_key(lang: str, gid: str, topic: str):
        hint = ctx_for(lang).topic_hints.get(topic, 0.0)
        return (gid in recent, -hint, rng.random())

    # кандидаты по классам
    pools: dict[str, dict[str, list[Any]]] = {"exec": {}, "predict": {}, "quiz": {}, "approach": {}}
    for lang in weights:
        gens = eligible(lang, grade, code_exec=code_exec, java_ok=java_ok)
        pools["exec"][lang] = sorted([g for g in gens if g.kind in Kind.EXECUTABLE], key=lambda g: rank_key(lang, g.id, g.topic))
        pools["predict"][lang] = sorted([g for g in gens if g.kind == Kind.PREDICT], key=lambda g: rank_key(lang, g.id, g.topic))
        pools["approach"][lang] = [g for g in gens if g.kind == Kind.APPROACH]
        pools["quiz"][lang] = sorted([i for i in quiz_pool if i["language"] == lang and i["grade"] == grade],
                                     key=lambda i: rank_key(lang, f"item:{i['id']}", i.get("topic", "")))
    selected: list[tuple[str, str, Any]] = []   # (class, lang, generator|item)
    used_gen: dict[str, int] = {}
    order = sorted(weights, key=lambda l: -weights[l])

    def take(cls: str, count: int) -> int:
        got = 0
        # круговой обход по языкам с учётом весов: язык с большим весом получает больше «ходов»
        turns: list[str] = []
        for lang in order:
            turns += [lang] * max(1, round(weights[lang] * 4))
        guard = 0
        while got < count and guard < 200:
            guard += 1
            progressed = False
            for lang in turns:
                if got >= count:
                    break
                pool = pools[cls][lang]
                while pool:
                    cand = pool.pop(0)
                    cid = cand.id if isinstance(cand, GeneratorDef) else f"item:{cand['id']}"
                    if used_gen.get(cid, 0) >= (2 if isinstance(cand, GeneratorDef) and cand.kind != Kind.APPROACH else 1):
                        continue
                    used_gen[cid] = used_gen.get(cid, 0) + 1
                    if isinstance(cand, GeneratorDef) and used_gen[cid] < 2 and cand.kind != Kind.APPROACH:
                        pool.append(cand)        # допускаем второй экземпляр с другими параметрами
                    selected.append((cls, lang, cand))
                    got += 1
                    progressed = True
                    break
            if not progressed:
                break
        return got

    deficit = 0
    for cls in ("exec", "predict", "approach", "quiz"):
        deficit += q[cls] - take(cls, q[cls])
    for cls in ("quiz", "predict", "exec"):       # недобор перераспределяем
        if deficit <= 0:
            break
        deficit -= take(cls, deficit)

    specs: list[TaskSpec] = []
    for idx, (cls, lang, cand) in enumerate(selected):
        try:
            if isinstance(cand, GeneratorDef):
                s = sub_seed(seed, cand.id, idx)
                spec = cand.build(random.Random(s), ctx_for(lang), grade, s)
            else:
                spec = _quiz_spec(cand, seed, grade)
            _sanity(spec)
            specs.append(spec)
        except Exception:      # генератор не должен ломать выдачу теста; проблема видна в validate_bank
            continue
    order_key = {Kind.QUIZ_SINGLE: 0, Kind.QUIZ_MULTI: 0, Kind.PREDICT: 1, Kind.SQL_QUERY: 2, Kind.CODE_FUNCTION: 3, Kind.APPROACH: 4}
    specs.sort(key=lambda s: order_key.get(s.kind, 9))
    return specs


def session_time_limit(specs: list[TaskSpec], purpose: str) -> int:
    total = int(sum(s.time_limit_s for s in specs) * 0.8)
    lo, hi = (300, 900) if purpose == "micro" else (900, 3600)
    return max(lo, min(hi, (total // 60) * 60))
