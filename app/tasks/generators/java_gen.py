"""Java-генераторы. Семантика Java (деление, переполнение int, кэш Integer, конкатенация, char) моделируется
в Python — поэтому «что выведет код» вычисляется без JVM. Две задачи с кодом выполняются в JDK (если доступен)."""
from __future__ import annotations

import random
from collections import Counter

from app.tasks.generators.choice_utils import build_options
from app.tasks.types import ContextPack, GeneratorDef, Kind, TaskSpec

_ST = "Что будет выведено при выполнении кода на Java? Выберите один вариант."


def _wrap32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def _java_div(a: int, b: int) -> tuple[int, int]:
    q = abs(a) // abs(b)
    q = q if (a >= 0) == (b >= 0) else -q
    return q, a - q * b


def _predict(gid, grade, topic, seed, rng, ctx, code, correct, distractors, difficulty, statement=_ST):
    options, _ = build_options(rng, correct, distractors)
    if len(options) < 3:
        raise RuntimeError(f"not enough options for {gid}")
    return TaskSpec(gid, Kind.PREDICT, "java", grade, topic, seed, statement,
                    public={"code": code, "options": options, "code_language": "java"},
                    private={"correct": correct}, difficulty=difficulty, time_limit_s=120, sources=list(ctx.sources[:2]))


def _int_division(rng, ctx, grade, seed):
    while True:
        a, b = rng.randint(-45, 45), rng.randint(-9, 9)
        if b != 0 and a % b != 0 and (a < 0) != (b < 0):
            break
    q, r = _java_div(a, b)
    code = (f"int a = {a}, b = {b};\nSystem.out.println(a / b);\nSystem.out.println(a % b);")
    correct = f"{q}, {r}"
    py_q, py_r = a // b, a % b
    return _predict("java.intern.int_division", grade, "integer_division_modulo", seed, rng, ctx, code, correct,
                    [f"{py_q}, {py_r}", f"{q}, {py_r}", f"{py_q}, {r}", f"{q}, {abs(r)}"], -1.0,
                    "Какие два значения будут выведены (по одному в строке)?")


def _string_concat(rng, ctx, grade, seed):
    a, b, c, d = [rng.randint(1, 9) for _ in range(4)]
    code = f'System.out.println({a} + {b} + "x" + {c} + {d});'
    return _predict("java.intern.string_concat", grade, "operators_string_concat", seed, rng, ctx, code,
                    f"{a + b}x{c}{d}", [f"{a}{b}x{c}{d}", f"{a + b}x{c + d}", f"{a}{b}x{c + d}", f"{a + b + c + d}"], -0.9)


def _integer_cache(rng, ctx, grade, seed):
    n = rng.choice([100, 127, 128, 1000, -128, -129, 500, 42])
    code = f"Integer x = {n};\nInteger y = {n};\nSystem.out.println((x == y) + \" \" + x.equals(y));"
    correct = f"{'true' if -128 <= n <= 127 else 'false'} true"
    return _predict("java.junior.integer_cache", grade, "boxing_integer_cache", seed, rng, ctx, code, correct,
                    ["true true", "false true", "true false", "false false"], -0.2)


def _int_overflow(rng, ctx, grade, seed):
    k = rng.randint(1, 5)
    j = rng.randint(k + 1, k + 10)
    code = f"int x = Integer.MAX_VALUE - {k};\nx += {j};\nSystem.out.println(x);"
    true_val = 2147483647 - k + j
    correct = str(_wrap32(true_val))
    return _predict("java.junior.int_overflow", grade, "int_overflow", seed, rng, ctx, code, correct,
                    [str(true_val), "2147483647", "-2147483648", str(-true_val), "ArithmeticException"], -0.1)


def _char_arith(rng, ctx, grade, seed):
    n = rng.randint(1, 20)
    ch = chr(ord("a") + n)
    code = f"char c = 'a';\nc += {n};\nSystem.out.println(c);\nSystem.out.println(c + 1);"
    num = ord(ch) + 1
    return _predict("java.middle.char_arith", grade, "char_arithmetic", seed, rng, ctx, code, f"{ch}, {num}",
                    [f"{ord(ch)}, {num}", f"{ch}, {chr(ord(ch) + 1)}", f"{ch}, {ord(ch)}", f"{chr(ord('a') + n - 1)}, {num}"],
                    0.5, "Какие два значения будут выведены (по одному в строке)?")


# ---------------------------------------------------------------------------- функции (JDK)

def _fn_task(gid, grade, topic, seed, ctx, statement, signature, starter, tests, examples, difficulty, fmt):
    return TaskSpec(gid, Kind.CODE_FUNCTION, "java", grade, topic, seed, statement,
                    public={"signature": signature, "starter": starter, "examples": examples, "result_format": fmt,
                            "note": "Класс должен называться Solution, метод — solve. Допустимы импорты из java.util."},
                    private={"tests": tests, "result_format": fmt}, difficulty=difficulty, time_limit_s=420,
                    sources=list(ctx.sources[:2]))


def _java_sum_multiples(rng, ctx, grade, seed):
    a, b = rng.sample(range(2, 10), 2)

    def ref(n):
        return sum(i for i in range(1, n) if i % a == 0 or i % b == 0)

    cases = [1, 2, 10] + [rng.randint(50, 20000) for _ in range(5)]
    tests = [{"java_args": [str(n)], "expected_str": str(ref(n))} for n in cases]
    return _fn_task(
        "java.junior.sum_multiples", grade, "loops_conditions", seed, ctx,
        f"Реализуйте метод solve(n): сумма всех натуральных чисел от 1 до n-1 включительно, которые делятся на {a} или на {b}. "
        f"Результат может не помещаться в int — используйте long.", "static long solve(int n)",
        "class Solution {\n    static long solve(int n) {\n        return 0;\n    }\n}\n", tests,
        [{"input": "10", "output": str(ref(10))}], -0.6, "scalar")


def _java_merge_intervals(rng, ctx, grade, seed):
    g = rng.choice([0, 1, 2, 3])

    def ref(iv):
        out: list[list[int]] = []
        for s_, e_ in sorted(iv):
            if out and s_ <= out[-1][1] + g:
                out[-1][1] = max(out[-1][1], e_)
            else:
                out.append([s_, e_])
        return out

    def lit(iv):
        return "new int[][]{" + ",".join("{" + f"{s_},{e_}" + "}" for s_, e_ in iv) + "}"

    def rnd(k):
        res = []
        for _ in range(k):
            s_ = rng.randint(0, 60)
            res.append([s_, s_ + rng.randint(0, 12)])
        return res

    cases = [[], [[1, 2]], [[1, 3], [3 + g, 5 + g]]] + [rnd(rng.randint(3, 12)) for _ in range(5)]
    tests = [{"java_args": [lit(c)], "expected_str": str(ref(c))} for c in cases]
    ex = [[1, 3], [4, 6], [9, 10]]
    return _fn_task(
        "java.middle.merge_intervals", grade, "arrays_sorting", seed, ctx,
        f"Реализуйте метод solve(intervals): объедините отрезки [start, end], если start следующего не больше "
        f"end предыдущего более чем на {g} (start <= end + {g}). Результат отсортирован по началу по возрастанию; "
        f"вход может быть не отсортирован.", "static int[][] solve(int[][] intervals)",
        "class Solution {\n    static int[][] solve(int[][] intervals) {\n        return new int[0][];\n    }\n}\n", tests,
        [{"input": str(ex), "output": str(ref(ex))}], 0.6, "deep")


JAVA_GENERATORS = [
    GeneratorDef("java.intern.int_division", "java", Kind.PREDICT, "integer_division_modulo", ("intern", "junior"), -1.0, ("int", "деление", "operator"), _int_division),
    GeneratorDef("java.intern.string_concat", "java", Kind.PREDICT, "operators_string_concat", ("intern",), -0.9, ("string", "строк", "concat"), _string_concat),
    GeneratorDef("java.junior.integer_cache", "java", Kind.PREDICT, "boxing_integer_cache", ("junior", "middle"), -0.2, ("integer", "boxing", "equals", "wrapper"), _integer_cache),
    GeneratorDef("java.junior.int_overflow", "java", Kind.PREDICT, "int_overflow", ("junior", "middle"), -0.1, ("overflow", "переполн", "int", "long"), _int_overflow),
    GeneratorDef("java.middle.char_arith", "java", Kind.PREDICT, "char_arithmetic", ("middle", "senior"), 0.5, ("char", "unicode", "кодир"), _char_arith),
    GeneratorDef("java.junior.sum_multiples", "java", Kind.CODE_FUNCTION, "loops_conditions", ("junior", "intern"), -0.6, ("цикл", "loop", "алгоритм"), _java_sum_multiples, needs_code_exec=True, time_limit_s=420),
    GeneratorDef("java.middle.merge_intervals", "java", Kind.CODE_FUNCTION, "arrays_sorting", ("middle", "senior"), 0.6, ("array", "массив", "sort", "interval", "collections"), _java_merge_intervals, needs_code_exec=True, time_limit_s=420),
]
