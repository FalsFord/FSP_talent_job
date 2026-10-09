"""Python-генераторы: «что выведет код» (ответ вычисляется выполнением доверенного шаблона, варианты ответа —
выводы мутированных шаблонов) и функции с автопроверкой на скрытых тестах."""
from __future__ import annotations

import random
from collections import Counter, OrderedDict

from app.tasks.generators.choice_utils import build_options, numeric_fillers, run_trusted
from app.tasks.types import ContextPack, GeneratorDef, Kind, TaskSpec

_PREDICT_STATEMENT = "Что будет выведено в результате выполнения кода? Выберите один вариант."


def _predict(gid, grade, topic, seed, rng, ctx, code, mutants, difficulty) -> TaskSpec:
    correct = run_trusted(code)
    distractors = [run_trusted(m) for m in mutants]
    distractors += numeric_fillers(rng, correct)
    options, _ = build_options(rng, correct, distractors)
    if len(options) < 3:
        raise RuntimeError(f"not enough distinct options for {gid}")
    return TaskSpec(
        gid, Kind.PREDICT, "python", grade, topic, seed, _PREDICT_STATEMENT,
        public={"code": code, "options": options, "code_language": "python"},
        private={"correct": correct}, difficulty=difficulty, time_limit_s=120, sources=list(ctx.sources[:2]),
    )


def _slice_sum(rng, ctx, grade, seed):
    n = rng.randint(8, 11)
    nums = [rng.randint(1, 30) for _ in range(n)]
    s, e, k = rng.randint(0, 2), rng.randint(n - 3, n), rng.choice([2, 3])
    code = f"nums = {nums}\nprint(sum(nums[{s}:{e}:{k}]))"
    mutants = [f"nums = {nums}\nprint(sum(nums[{s}:{e - 1}:{k}]))", f"nums = {nums}\nprint(sum(nums[{s + 1}:{e}:{k}]))",
               f"nums = {nums}\nprint(sum(nums[{s}:{e}:1]))", f"nums = {nums}\nprint(sum(nums[{s}:{e + 1}:{k}]))"]
    return _predict("py.intern.slice_sum", grade, "slices", seed, rng, ctx, code, mutants, -1.2)


def _dict_counts(rng, ctx, grade, seed):
    letters = rng.sample("abcdefg", 4)
    words = [rng.choice(letters) for _ in range(rng.randint(7, 10))]
    body = "counts = {}\nfor w in words:\n    counts[w] = counts.get(w, {d}) + 1\nprint(sorted(counts.items()))"
    code = f"words = {words}\n" + body.replace("{d}", "0")
    mutants = [f"words = {words}\n" + body.replace("{d}", "1"),
               f"words = {words}\ncounts = {{}}\nfor w in words:\n    counts[w] = 1\nprint(sorted(counts.items()))",
               f"words = {words}\nprint(sorted(set(words)))",
               f"words = {words}\nprint(sorted(Counter(words).items()) if False else len(set(words)))"]
    return _predict("py.intern.dict_counts", grade, "dict_counting", seed, rng, ctx, code, mutants, -1.0)


def _mutable_default(rng, ctx, grade, seed):
    a, b, c = rng.sample(range(1, 50), 3)
    z = rng.randint(50, 99)
    code = f"def add(x, acc=[]):\n    acc.append(x)\n    return acc\nprint(add({a}), add({b}), add({c}, [{z}]))"
    fixed = (f"def add(x, acc=None):\n    acc = [] if acc is None else acc\n    acc.append(x)\n    return acc\n"
             f"print(add({a}), add({b}), add({c}, [{z}]))")
    sep = (f"def add(x, acc=[]):\n    acc.append(x)\n    return acc\nr1 = add({a})\nprint(r1, [{b}], [{z}, {c}])")
    return _predict("py.junior.mutable_default", grade, "mutable_default_args", seed, rng, ctx, code,
                    [fixed, sep, f"print([{a}], [{a}, {b}], [{z}, {c}])"], -0.3)


def _shallow_copy(rng, ctx, grade, seed):
    x, y, z, w, v = [rng.randint(1, 9) for _ in range(5)]
    code = (f"import copy\na = [[{x}, {y}], [{z}]]\nb = a.copy()\nc = copy.deepcopy(a)\na[0].append({w})\n"
            f"a.append([{v}])\nprint(len(b), len(b[0]), len(c[0]))")
    mutants = [code.replace("b = a.copy()", "b = a"), code.replace("copy.deepcopy(a)", "a.copy()"),
               code.replace("b = a.copy()", "b = copy.deepcopy(a)")]
    return _predict("py.junior.shallow_copy", grade, "shallow_vs_deep_copy", seed, rng, ctx, code, mutants, -0.1)


def _late_binding(rng, ctx, grade, seed):
    n, m = rng.randint(3, 5), rng.randint(2, 6)
    code = f"funcs = [lambda: i * {m} for i in range({n})]\nprint([f() for f in funcs])"
    mutants = [code.replace("lambda:", "lambda i=i:"), f"print([i * {m} for i in range({n})][::-1])",
               f"funcs = [lambda: i * {m} for i in range({n})]\nprint([f() for f in funcs][:1])"]
    return _predict("py.middle.late_binding", grade, "closures_late_binding", seed, rng, ctx, code, mutants, 0.5)


def _generator_exhaust(rng, ctx, grade, seed):
    n, m = rng.randint(4, 7), rng.randint(2, 5)
    code = f"g = (x * {m} for x in range({n}))\nprint(sum(g), sum(g), len(list(g)))"
    mutants = [f"g = [x * {m} for x in range({n})]\nprint(sum(g), sum(g), len(list(g)))",
               f"g = (x * {m} for x in range({n}))\nprint(sum(g), 0, 0 + 1)"]
    return _predict("py.middle.generator_exhaust", grade, "generators_one_shot", seed, rng, ctx, code, mutants, 0.7)


def _dict_mutation(rng, ctx, grade, seed):
    keys = rng.sample(range(1, 30), 4)
    code = (f"d = {{k: k for k in {keys}}}\ntry:\n    for k in d:\n        d[k + 100] = 0\nexcept RuntimeError:\n"
            f"    print('error')\nprint(len(d))")
    mutants = [code.replace("for k in d:", "for k in list(d):"), code.replace("d[k + 100] = 0", "d[k] = 0"),
               code.replace("print('error')\nprint(len(d))", "print('error')\nprint(len(d) + 1)")]
    return _predict("py.senior.dict_mutation", grade, "dict_mutation_during_iteration", seed, rng, ctx, code, mutants, 1.2)


def _decorator_order(rng, ctx, grade, seed):
    n = rng.randint(2, 9)
    a, b = rng.sample("ABCDEF", 2)
    code = (f"def {a.lower()}(f):\n    def w(*args):\n        return '{a}(' + f(*args) + ')'\n    return w\n"
            f"def {b.lower()}(f):\n    def w(*args):\n        return '{b}(' + f(*args) + ')'\n    return w\n"
            f"@{a.lower()}\n@{b.lower()}\ndef hello(x):\n    return str(x)\nprint(hello({n}))")
    swapped = code.replace(f"@{a.lower()}\n@{b.lower()}", f"@{b.lower()}\n@{a.lower()}")
    return _predict("py.senior.decorator_order", grade, "decorators", seed, rng, ctx, code,
                    [swapped, f"print('{a}({b}({n}))')".replace(f"'{a}", f"'{b}")],
                    1.0)


# ---------------------------------------------------------------------------------- функции

def _function_task(gid, grade, topic, seed, ctx, statement, signature, starter, tests, examples, difficulty, tl=300):
    return TaskSpec(
        gid, Kind.CODE_FUNCTION, "python", grade, topic, seed, statement,
        public={"signature": signature, "starter": starter, "examples": examples, "entry": "solve",
                "allowed_imports": "math, itertools, functools, collections, heapq, bisect, re, string, typing, "
                                   "dataclasses, operator, statistics, decimal, fractions, datetime, json, copy"},
        private={"tests": tests}, difficulty=difficulty, time_limit_s=tl, sources=list(ctx.sources[:2]),
    )


def _sum_multiples(rng, ctx, grade, seed):
    # Константы a, b входят в условие и различаются между попытками: чужое решение с «зашитыми» a, b не пройдёт.
    a, b = rng.sample(range(2, 10), 2)

    def ref(n):
        return sum(i for i in range(1, n) if i % a == 0 or i % b == 0)

    cases = [1, 2, 10] + [rng.randint(50, 20000) for _ in range(5)]
    tests = [{"args": [n], "expected": ref(n)} for n in cases]
    return _function_task(
        "py.intern.sum_multiples", grade, "loops_conditions", seed, ctx,
        f"Напишите функцию solve(n): сумма всех натуральных чисел от 1 до n-1 включительно, которые делятся "
        f"на {a} или на {b}.", "def solve(n: int) -> int", "def solve(n):\n    ...\n",
        tests, [{"args": [10], "expected": ref(10)}], -1.1)


def _group_first_letter(rng, ctx, grade, seed):
    pool = ["Apple", "apricot", "Banana", "blueberry", "cherry", "Cranberry", "date", "Dragonfruit", "elder", "fig",
            "Fennel", "grape", "Guava", "kiwi", "lemon", "Lime", "mango", "melon", "plum", "peach"]
    rule = rng.choice(["first", "last", "length"])
    min_count = rng.choice([1, 2, 3])  # в результат попадают только ключи, встретившиеся не менее min_count раз
    key = {"first": lambda w: w[0].lower(), "last": lambda w: w[-1].lower(), "length": lambda w: str(len(w))}[rule]
    what = {"first": "первой буквы (в нижнем регистре)", "last": "последней буквы (в нижнем регистре)",
            "length": "длины слова (ключ — строка, например '5')"}[rule]

    def ref(words):
        out: dict[str, int] = {}
        for w in words:
            out[key(w)] = out.get(key(w), 0) + 1
        return {k: v for k, v in out.items() if v >= min_count}

    for _ in range(20):   # узкая подвыборка слов даёт повторы ключей: при min_count>1 ответы не вырождаются в {}
        sub = rng.sample(pool, 6)
        cases = [[], ["Zed"]] + [[rng.choice(sub) for _ in range(rng.randint(8, 20))] for _ in range(6)]
        tests = [{"args": [c], "expected": ref(c)} for c in cases]
        if len({repr(t["expected"]) for t in tests}) >= 4:
            break
    ex = ["Apple", "avocado", "Bean"]
    return _function_task(
        "py.junior.group_first_letter", grade, "dict_processing", seed, ctx,
        f"Напишите функцию solve(words): верните словарь {{ключ: количество слов}}, где ключ — значение "
        f"{what}. В словарь включайте только ключи, встретившиеся не менее {min_count} раз.", "def solve(words: list[str]) -> dict[str, int]", "def solve(words):\n    ...\n",
        tests, [{"args": [ex], "expected": ref(ex)}], -0.4)


def _merge_intervals(rng, ctx, grade, seed):
    g = rng.choice([0, 1, 2, 3])  # допуск: объединять, если следующий start <= предыдущий end + g
    desc = rng.choice([False, True])  # порядок результата

    def ref(iv):
        out: list[list[int]] = []
        for s_, e_ in sorted(iv):
            if out and s_ <= out[-1][1] + g:
                out[-1][1] = max(out[-1][1], e_)
            else:
                out.append([s_, e_])
        return out[::-1] if desc else out

    def rnd(k):
        res = []
        for _ in range(k):
            s_ = rng.randint(0, 60)
            res.append([s_, s_ + rng.randint(0, 12)])
        return res

    cases = [[], [[1, 2]], [[1, 3], [3 + g, 5 + g]]] + [rnd(rng.randint(3, 12)) for _ in range(5)]
    tests = [{"args": [c], "expected": ref(c)} for c in cases]
    ex = [[1, 3], [4, 6], [9, 10]]
    return _function_task(
        "py.middle.merge_intervals", grade, "sorting_intervals", seed, ctx,
        f"Напишите функцию solve(intervals): объедините отрезки [start, end], если начало следующего отрезка не "
        f"больше конца предыдущего более чем на {g} (то есть start <= end + {g}). Результат — список отрезков, "
        f"отсортированный по началу {'по убыванию' if desc else 'по возрастанию'}; вход может быть не отсортирован.",
        "def solve(intervals: list[list[int]]) -> list[list[int]]", "def solve(intervals):\n    ...\n", tests,
        [{"args": [ex], "expected": ref(ex)}], 0.5)


def _top_k_frequent(rng, ctx, grade, seed):
    vocab = ["red", "green", "blue", "cyan", "pink", "gray", "gold", "teal", "navy"]
    k = rng.randint(2, 4)
    asc = rng.choice([True, False])  # порядок слов при равной частоте
    min_freq = rng.choice([1, 2])    # слова реже min_freq раз не учитываются

    def ref(words):
        c = Counter(words)
        key = (lambda x: (-x[1], x[0])) if asc else (lambda x: (-x[1], [-ord(ch) for ch in x[0]]))
        return [w for w, n in sorted(c.items(), key=key) if n >= min_freq][:k]

    cases = [[rng.choice(vocab[: rng.randint(3, 9)]) for _ in range(rng.randint(5, 30))] for _ in range(7)]
    tests = [{"args": [w], "expected": ref(w)} for w in cases]
    ex = ["a", "b", "a", "c", "b", "a", "c"]
    return _function_task(
        "py.middle.top_k_frequent", grade, "counting_sorting", seed, ctx,
        f"Напишите функцию solve(words): верните {k} самых частых слов (список строк); при равной частоте слова "
        f"упорядочиваются по алфавиту {'по возрастанию' if asc else 'по убыванию'}. Слова, встретившиеся реже {min_freq} раз, не учитываются. "
        f"Если подходящих слов меньше {k}, верните все.", "def solve(words: list[str]) -> list[str]", "def solve(words):\n    ...\n", tests,
        [{"args": [ex], "expected": ref(ex)}], 0.4)


def _lru_hits(rng, ctx, grade, seed):
    policy = rng.choice(["LRU", "FIFO", "MRU"])
    count_misses = rng.choice([False, True])

    def ref(cap, keys):
        cache: OrderedDict[int, None] = OrderedDict()
        hits = 0
        for k in keys:
            if k in cache:
                hits += 1
                if policy in ("LRU", "MRU"):
                    cache.move_to_end(k)
            else:
                if len(cache) >= cap:
                    cache.popitem(last=(policy == "MRU"))
                cache[k] = None
        return (len(keys) - hits) if count_misses else hits

    cases = [(1, []), (2, [1, 2, 1, 3, 2])]
    for _ in range(4):
        cases.append((rng.randint(2, 6), [rng.randint(1, 9) for _ in range(rng.randint(10, 60))]))
    big_cap = rng.randint(800, 1200)  # проверка эффективности: наивная реализация на списках может не уложиться
    cases.append((big_cap, [rng.randint(1, big_cap * 2) for _ in range(60000)]))
    tests = [{"args": [c, k], "expected": ref(c, k)} for c, k in cases]
    rule = {
        "LRU": "при обращении к ключу из кэша он считается самым свежим; вытесняется наименее недавно использованный",
        "FIFO": "порядок вытеснения определяется только временем добавления (обращение к ключу из кэша его не "
                "обновляет); вытесняется самый ранний добавленный",
        "MRU": "при обращении к ключу из кэша он считается самым свежим; при переполнении вытесняется НАИБОЛЕЕ "
               "недавно использованный ключ (до добавления нового)",
    }[policy]
    what = "число промахов (miss)" if count_misses else "число попаданий (hit)"
    return _function_task(
        "py.senior.lru_hits", grade, "cache_policy_efficiency", seed, ctx,
        f"Напишите функцию solve(capacity, keys): смоделируйте кэш ёмкости capacity с политикой {policy} и верните "
        f"{what}. Правило: {rule}. Последовательность может содержать десятки "
        f"тысяч обращений.", "def solve(capacity: int, keys: list[int]) -> int",
        "def solve(capacity, keys):\n    ...\n", tests, [{"args": [2, [1, 2, 1, 3, 2]], "expected": ref(2, [1, 2, 1, 3, 2])}],
        1.3, tl=420)


PYTHON_GENERATORS = [
    GeneratorDef("py.intern.slice_sum", "python", Kind.PREDICT, "slices", ("intern",), -1.2, ("slice", "срез", "list"), _slice_sum),
    GeneratorDef("py.intern.dict_counts", "python", Kind.PREDICT, "dict_counting", ("intern", "junior"), -1.0, ("dict", "словар", "counter"), _dict_counts),
    GeneratorDef("py.junior.mutable_default", "python", Kind.PREDICT, "mutable_default_args", ("junior", "middle"), -0.3, ("default", "mutable", "аргумент"), _mutable_default),
    GeneratorDef("py.junior.shallow_copy", "python", Kind.PREDICT, "shallow_vs_deep_copy", ("junior", "middle"), -0.1, ("copy", "копирован", "deepcopy"), _shallow_copy),
    GeneratorDef("py.middle.late_binding", "python", Kind.PREDICT, "closures_late_binding", ("middle", "senior"), 0.5, ("closure", "замыкан", "lambda"), _late_binding),
    GeneratorDef("py.middle.generator_exhaust", "python", Kind.PREDICT, "generators_one_shot", ("middle", "senior"), 0.7, ("generator", "генератор", "yield", "iterator"), _generator_exhaust),
    GeneratorDef("py.senior.dict_mutation", "python", Kind.PREDICT, "dict_mutation_during_iteration", ("senior", "lead"), 1.2, ("dict", "iteration", "итерац", "runtime"), _dict_mutation),
    GeneratorDef("py.senior.decorator_order", "python", Kind.PREDICT, "decorators", ("senior", "middle"), 1.0, ("decorator", "декоратор", "wraps"), _decorator_order),
    GeneratorDef("py.intern.sum_multiples", "python", Kind.CODE_FUNCTION, "loops_conditions", ("intern", "junior"), -1.1, ("loop", "цикл", "алгоритм"), _sum_multiples, needs_code_exec=True),
    GeneratorDef("py.junior.group_first_letter", "python", Kind.CODE_FUNCTION, "dict_processing", ("junior",), -0.4, ("dict", "строк", "string", "парс", "обработк"), _group_first_letter, needs_code_exec=True),
    GeneratorDef("py.middle.merge_intervals", "python", Kind.CODE_FUNCTION, "sorting_intervals", ("middle", "junior"), 0.5, ("interval", "sort", "сортиров", "расписан"), _merge_intervals, needs_code_exec=True),
    GeneratorDef("py.middle.top_k_frequent", "python", Kind.CODE_FUNCTION, "counting_sorting", ("middle",), 0.4, ("counter", "частот", "top", "лог", "log"), _top_k_frequent, needs_code_exec=True),
    GeneratorDef("py.senior.lru_hits", "python", Kind.CODE_FUNCTION, "lru_cache_efficiency", ("senior", "lead"), 1.3, ("cache", "кэш", "lru", "ttl", "in-memory"), _lru_hits, needs_code_exec=True, time_limit_s=420),
]
