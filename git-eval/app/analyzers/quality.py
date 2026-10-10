"""Качество кода. Для Python: разбор AST (код НЕ выполняется) + ruff. Для остальных языков — только грубые метрики."""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
from collections import Counter

from .common import Ctx, Result, clamp, finding, lang_of, wavg


def _ruff(ctx: Ctx) -> dict | None:
    exe = shutil.which("ruff")
    if not exe:
        return None
    try:
        # --isolated: игнорируем конфиг самого репозитория; ruff только читает файлы, ничего не исполняет
        p = subprocess.run([exe, "check", "--isolated", "--no-cache", "--output-format", "json",
                            "--select", "E,F,B", "--ignore", "E501", str(ctx.root)],
                           capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p.returncode not in (0, 1):
        return None
    try:
        items = json.loads(p.stdout or b"[]")
    except ValueError:
        return None
    return {"total": len(items), "by_code": Counter(i.get("code") for i in items).most_common(5)}


def _python(ctx: Ctx, files: list[str]) -> Result:
    f: list[dict] = []
    broken = 0
    funcs = []                       # (length, has_doc, annotated, public)
    bare_except = 0
    loc = 0
    for rel in files:
        src = ctx.text(rel)
        loc += ctx.loc(rel)
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            broken += 1
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                params = a.posonlyargs + a.args + a.kwonlyargs
                annotated = node.returns is not None or any(p.annotation for p in params if p.arg not in ("self", "cls"))
                funcs.append(((node.end_lineno or node.lineno) - node.lineno + 1,
                              ast.get_docstring(node) is not None, annotated, not node.name.startswith("_")))
            elif isinstance(node, ast.ExceptHandler) and node.type is None:
                bare_except += 1

    parts: list[tuple[float, float]] = []
    parse_s = 1 - broken / len(files)
    parts.append((parse_s, 0.25))
    if broken:
        f.append(finding("bad", "syntax_errors", f"Файлов с синтаксическими ошибками: {broken} из {len(files)}"))

    metrics: dict = {"python_files": len(files), "python_loc": loc, "syntax_errors": broken, "functions": len(funcs),
                     "bare_except": bare_except}
    if funcs:
        avg_len = sum(x[0] for x in funcs) / len(funcs)
        max_len = max(x[0] for x in funcs)
        len_s = 1.0 if avg_len <= 25 else 0.6 if avg_len <= 50 else 0.3
        if max_len > 150:
            len_s = max(0.0, len_s - 0.2)
            f.append(finding("warn", "huge_function", f"Есть функция на {max_len} строк"))
        parts.append((len_s, 0.25))
        pub = [x for x in funcs if x[3]]
        doc_share = sum(x[1] for x in pub) / len(pub) if pub else 1.0
        ann_share = sum(x[2] for x in funcs) / len(funcs)
        parts.append(((doc_share + ann_share) / 2, 0.20))
        metrics.update(avg_function_len=round(avg_len, 1), max_function_len=max_len,
                       docstring_share=round(doc_share, 2), annotation_share=round(ann_share, 2))
        if doc_share < 0.2 and ann_share < 0.2:
            f.append(finding("info", "no_docs_types", "Почти нет докстрингов и аннотаций типов"))
    if bare_except:
        f.append(finding("warn", "bare_except", f"Голых `except:` в коде: {bare_except}"))

    rf = _ruff(ctx)
    if rf is not None:
        density = rf["total"] / max(loc / 1000, 0.2)
        parts.append((1.0 if density <= 5 else 0.7 if density <= 20 else 0.4 if density <= 50 else 0.1, 0.30))
        metrics.update(ruff_violations=rf["total"], ruff_per_kloc=round(density, 1), ruff_top=rf["by_code"])
        if density > 20:
            f.append(finding("warn", "lint", f"Много замечаний линтера: {rf['total']} ({round(density)} на 1000 строк)"))
    else:
        metrics["ruff"] = "unavailable"
    return Result("quality", round(clamp(wavg(parts)), 3), metrics, f)


def _generic(ctx: Ctx, files: list[str]) -> Result:
    sizes = [ctx.loc(x) for x in files]
    big_share = sum(s > 500 for s in sizes) / len(sizes)
    f = [finding("info", "limited_analysis", "Для этого языка выполнен только грубый анализ (размер файлов)")]
    if big_share > 0.3:
        f.append(finding("warn", "big_files", f"{round(big_share * 100)}% файлов длиннее 500 строк"))
    return Result("quality", round(clamp(1 - 1.5 * big_share), 3),
                  {"files": len(files), "avg_loc": round(sum(sizes) / len(sizes), 1), "limited": True}, f)


def analyze(ctx: Ctx) -> Result:
    src = ctx.source_files
    if not src:
        return Result("quality", 0.0, {"source_files": 0},
                      [finding("bad", "no_source", "В репозитории не найдено исходного кода")])
    py = [x for x in src if lang_of(x) == "python"]
    if ctx.language == "python" or (ctx.language is None and len(py) >= len(src) / 2):
        if py:
            return _python(ctx, py)
    return _generic(ctx, src)
