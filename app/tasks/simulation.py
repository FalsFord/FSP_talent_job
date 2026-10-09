"""Синтетическая валидация механики тестирования (воспроизводимая: python -m app.tasks.simulation).

ВАЖНО: это проверка внутренней согласованности механики на ЗАДАННОЙ модели кандидатов, а не доказательство
валидности на реальных людях. Модель: у кандидата скрытая способность θ; вероятность верного ответа на задание
сложности b — логистическая (с «угадыванием» для вопросов с выбором). Для заданий SQL «верный» ответ — эталонный запрос,
«неверный» — мутированный эталон. Используются реальные генераторы, реальная сборка теста и реальные функции проверки."""
from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict

from app.domain import grade_policy as gp
from app.tasks.blueprint import compose_test
from app.tasks.grading import grade_answer
from app.tasks.quiz_bank import QUIZ_ITEMS
from app.tasks.types import GRADES, Kind, TaskSpec
from app.tasks.validation import _SQL_MUTATIONS

SPREAD = 0.35            # разброс способности внутри грейда


def grade_mean_difficulty(grade: str, langs=("python", "sql"), probes: int = 12) -> float:
    """Средняя сложность b заданий теста данного грейда (оценка по реальным генераторам и банку)."""
    bs = []
    for k in range(probes):
        specs = compose_test(seed=900 + k, grade=grade, languages=list(langs), n_items=12, purpose="onboarding", contexts={},
                             quiz_pool=QUIZ_ITEMS, code_exec=False, java_ok=False)
        bs += [s.difficulty for s in specs if s.kind != Kind.APPROACH]
    return statistics.mean(bs)


def true_theta(margin: float) -> dict[str, float]:
    """ДОПУЩЕНИЕ модели: специалист грейда G справляется с заданиями грейда G на margin выше их средней сложности."""
    return {g: grade_mean_difficulty(g) + margin for g in GRADES}


def p_correct(theta: float, b: float, guess: float) -> float:
    return guess + (1 - guess) / (1 + math.exp(-1.7 * (theta - b)))


def _wrong_sql(spec: TaskSpec) -> str:
    ref = spec.private["reference_sql"]
    for old, new in _SQL_MUTATIONS:
        if old in ref:
            return ref.replace(old, new, 1)
    return "SELECT 1"


def answer_task(rng: random.Random, spec: TaskSpec, theta: float):
    if spec.kind in Kind.CHOICE:
        opts = spec.public["options"]
        correct = spec.private["correct"]
        if isinstance(correct, list):
            correct = correct[0]
        if rng.random() < p_correct(theta, spec.difficulty, 0.25):
            return {"value": correct}
        return {"value": rng.choice([o for o in opts if o != correct])}
    if spec.kind == Kind.SQL_QUERY:
        ok = rng.random() < p_correct(theta, spec.difficulty, 0.02)
        return {"value": spec.private["reference_sql"] if ok else _wrong_sql(spec)}
    if spec.kind == Kind.APPROACH:
        return {"value": ""}                  # рубричные задания в симуляции не участвуют
    return {"value": ""}


def take_test(rng, theta: float, grade: str, seed: int, langs=("python", "sql"), n=12, pass_ratio=gp.PASS_RATIO):
    specs = compose_test(seed=seed, grade=grade, languages=list(langs), n_items=n, purpose="onboarding", contexts={},
                         quiz_pool=QUIZ_ITEMS, code_exec=False, java_ok=False)
    specs = [s for s in specs if s.kind != Kind.APPROACH]        # рубрики оцениваются вручную/отдельно
    items = []
    for s in specs:
        res = grade_answer(s.kind, s.language, s.public, s.private, answer_task(rng, s, theta))
        items.append((res.score, s.weight))
    ratio, frac = gp.session_ratio(items)
    return ratio, gp.classify_result(ratio, gp.confidence_from(frac, []), pass_ratio, min(gp.BORDER_RATIO, pass_ratio - 0.05)), specs


def leak_key(s: TaskSpec) -> tuple:
    """Как злоумышленник опознаёт условие: статический вопрос — по формулировке (перестановка вариантов не помогает
    защите), сгенерированное задание — по полному отпечатку параметров."""
    return ("static", s.generator_id, s.statement) if s.generator_id.startswith("item:") else ("gen", s.fingerprint())


def pearson(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def auc(pos, neg):
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else float("nan")


def run(n_per_grade: int = 40, seed: int = 2026, n_items: int = 12, margin: float = 0.6, pass_ratio: float = gp.PASS_RATIO,
        sections=("retest", "discrimination", "placement", "leak")) -> dict:
    rng = random.Random(seed)
    theta = true_theta(margin)
    cands = [(g, rng.gauss(theta[g], SPREAD)) for g in GRADES for _ in range(n_per_grade)]
    kw = dict(n=n_items, pass_ratio=pass_ratio)
    out: dict = {"n_candidates": len(cands), "params": {"n_items": n_items, "margin": margin, "pass_ratio": pass_ratio},
                 "assumptions": {"true_theta": {k: round(v, 2) for k, v in theta.items()}, "spread": SPREAD}}

    # 1. Повторяемость: два прохождения теста своего грейда на разных вариантах
    r1, r2, same = [], [], 0
    for i, (g, th) in enumerate(cands):
        a, ra, _ = take_test(rng, th, g, seed * 7 + i, **kw)
        b, rb, _ = take_test(rng, th, g, seed * 7 + 10_000 + i, **kw)
        r1.append(a), r2.append(b)
        same += ra == rb
    out["test_retest"] = {"pearson_r": round(pearson(r1, r2), 3), "same_decision_rate": round(same / len(cands), 3)}

    # 2. Разделяющая способность: тест уровня «middle» для кандидатов ниже и не ниже middle
    lo, hi = [], []
    for i, (g, th) in enumerate(cands):
        ratio, _, _ = take_test(rng, th, "middle", seed * 13 + i, **kw)
        (hi if GRADES.index(g) >= GRADES.index("middle") else lo).append(ratio)
    out["discrimination_middle_test"] = {
        "auc_(>=middle vs <middle)": round(auc(hi, lo), 3),
        "mean_ratio_>=middle": round(statistics.mean(hi), 3), "mean_ratio_<middle": round(statistics.mean(lo), 3)}

    # 3. Определение грейда: кандидат заявляет грейд на 1 выше истинного (завышение), при неудаче идёт ниже
    exact = within1 = 0
    confusion: dict = defaultdict(lambda: defaultdict(int))
    for i, (g, th) in enumerate(cands):
        true_i = GRADES.index(g)
        assigned = None
        for lvl in range(min(4, true_i + 1), -1, -1):
            _, res, _ = take_test(rng, th, GRADES[lvl], seed * 17 + i * 5 + lvl, **kw)
            if res == "pass":
                assigned = lvl
                break
        assigned = 0 if assigned is None else assigned
        exact += assigned == true_i
        within1 += abs(assigned - true_i) <= 1
        confusion[g][GRADES[assigned]] += 1
    out["placement_with_overstated_declaration"] = {
        "exact_match": round(exact / len(cands), 3), "within_one_grade": round(within1 / len(cands), 3),
        "confusion": {k: dict(v) for k, v in confusion.items()}}

    # 4. Устойчивость к утечке: злоумышленник знает ключ ответов ПРЕДЫДУЩЕЙ попытки другого кандидата
    # (выписал правильные ответы по тексту/коду условия). Применимо только если условие повторилось дословно.
    gain, reuse_rates = [], {"generated": [], "static_quiz": []}
    for i in range(min(len(cands), 120)):
        g, th = cands[i]
        _, _, leaked_specs = take_test(rng, th, "middle", seed * 19 + i, **kw)
        key = {leak_key(s): s.private for s in leaked_specs}
        _, _, specs = take_test(rng, -2.0, "middle", seed * 19 + 50_000 + i, **kw)           # слабый кандидат с «шпаргалкой»
        items, honest_items, gen_hit = [], [], [0, 0]
        for s in specs:
            known = key.get(leak_key(s))
            static = s.generator_id.startswith("item:")
            reuse_rates["static_quiz" if static else "generated"].append(1.0 if known else 0.0)
            if s.kind in Kind.CHOICE:
                ans = {"value": known["correct"]} if known else answer_task(rng, s, -2.0)
            elif s.kind == Kind.SQL_QUERY:
                ans = {"value": known["reference_sql"]} if known else answer_task(rng, s, -2.0)
            else:
                continue
            items.append((grade_answer(s.kind, s.language, s.public, s.private, ans).score, s.weight))
            honest_items.append((grade_answer(s.kind, s.language, s.public, s.private, answer_task(rng, s, -2.0)).score, s.weight))
        gain.append(gp.session_ratio(items)[0] - gp.session_ratio(honest_items)[0])
    out["leak_resistance_middle"] = {
        "mean_score_gain_from_cheat_sheet": round(statistics.mean(gain), 3),
        "share_of_items_repeating_verbatim": {k: round(statistics.mean(v), 3) for k, v in reuse_rates.items() if v}}
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))
