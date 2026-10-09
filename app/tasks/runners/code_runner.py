"""Запуск пользовательского кода (Python, Java) для заданий kind=code_function.

ВАЖНО О БЕЗОПАСНОСТИ. Это эшелонированная защита, а НЕ полноценная песочница:
  * статический AST-фильтр (запрет опасных импортов/имён/dunder-атрибутов),
  * отдельный процесс, пустое окружение, временный cwd, лимиты CPU/памяти/файлов (rlimit), жёсткий timeout,
  * ограниченные builtins и белый список импортов внутри процесса.
Выполнение выключено по умолчанию (settings.code_exec_enabled=False). В production запускайте этот код только
в отдельном изолированном раннере (контейнер без сети, gVisor/nsjail/Firecracker, отдельный хост).
"""
from __future__ import annotations

import ast
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

ALLOWED_IMPORTS = {
    "math", "itertools", "functools", "collections", "heapq", "bisect", "re", "string", "typing",
    "dataclasses", "operator", "statistics", "decimal", "fractions", "datetime", "json", "copy",
}
BANNED_NAMES = {
    "eval", "exec", "compile", "open", "input", "__import__", "globals", "locals", "vars",
    "breakpoint", "exit", "quit", "memoryview", "help", "dir",
}
ALLOWED_DUNDER_ATTRS = {
    "__init__", "__name__", "__eq__", "__lt__", "__le__", "__gt__", "__ge__", "__hash__", "__repr__", "__str__",
    "__len__", "__iter__", "__next__", "__getitem__", "__setitem__", "__contains__", "__call__", "__enter__",
    "__exit__", "__add__", "__sub__", "__mul__", "__post_init__", "__class_getitem__",
}


@dataclass
class CodeRunResult:
    passed: int = 0
    total: int = 0
    error: str | None = None            # код ошибки уровня запуска
    message: str = ""
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return self.passed / self.total if self.total else 0.0


class ForbiddenCode(Exception):
    pass


def static_check_python(code: str) -> None:
    if len(code) > 20_000:
        raise ForbiddenCode("Слишком длинный код")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ForbiddenCode(f"SyntaxError: {e.msg} (строка {e.lineno})") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise ForbiddenCode(f"Импорт модуля «{a.name}» запрещён")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise ForbiddenCode(f"Импорт из «{node.module}» запрещён")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise ForbiddenCode(f"Использование «{node.id}» запрещено")
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("__") and a.endswith("__") and a not in ALLOWED_DUNDER_ATTRS:
                raise ForbiddenCode(f"Доступ к «{a}» запрещён")
        elif isinstance(node, ast.Global):
            raise ForbiddenCode("global запрещён")


_PY_HARNESS = r'''
import sys, json, io, builtins, signal, contextlib
payload = json.loads(sys.stdin.read())
real_out = sys.stdout
ALLOWED = set(payload["allowed"])
real_import = builtins.__import__
def guarded_import(name, *a, **k):
    if name.split(".")[0] not in ALLOWED:
        raise ImportError("import of %s is not allowed" % name)
    return real_import(name, *a, **k)
safe = {k: getattr(builtins, k) for k in dir(builtins) if k not in set(payload["banned"])}
safe["__import__"] = guarded_import
ns = {"__builtins__": safe, "__name__": "__candidate__"}
class TO(Exception): pass
def on_alarm(sig, frm): raise TO()
signal.signal(signal.SIGALRM, on_alarm)
results = []
buf = io.StringIO()
fatal = None
try:
    with contextlib.redirect_stdout(buf):
        exec(compile(payload["code"], "<candidate>", "exec"), ns)
    fn = ns.get(payload["entry"])
    if not callable(fn):
        fatal = {"fatal": "NO_ENTRYPOINT"}
    else:
        for t in payload["tests"]:
            signal.setitimer(signal.ITIMER_REAL, payload["per_test_s"])
            try:
                with contextlib.redirect_stdout(buf):
                    out = fn(*json.loads(json.dumps(t["args"])))
                signal.setitimer(signal.ITIMER_REAL, 0)
                results.append({"ok": True, "out": json.loads(json.dumps(out))})
            except TO:
                results.append({"ok": False, "err": "TIMEOUT"})
            except BaseException as e:
                signal.setitimer(signal.ITIMER_REAL, 0)
                results.append({"ok": False, "err": type(e).__name__})
except SystemExit:
    pass
except BaseException as e:
    fatal = {"fatal": "COMPILE_OR_LOAD_ERROR", "msg": type(e).__name__ + ": " + str(e)[:200]}
real_out.write(json.dumps(fatal if fatal else {"results": results}))
'''


def _limits():  # выполняется в дочернем процессе до exec
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except Exception:
        pass


def _json_equal(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def run_python_function(code: str, tests: list[dict], *, entry: str = "solve", timeout_s: float = 10.0,
                        per_test_s: float = 2.0) -> CodeRunResult:
    res = CodeRunResult(total=len(tests))
    try:
        static_check_python(code)
    except ForbiddenCode as e:
        res.error, res.message = "FORBIDDEN_OR_INVALID", str(e)
        return res
    payload = json.dumps({
        "code": code, "entry": entry, "tests": [{"args": t["args"]} for t in tests], "per_test_s": per_test_s,
        "allowed": sorted(ALLOWED_IMPORTS), "banned": sorted(BANNED_NAMES),
    })
    with tempfile.TemporaryDirectory() as cwd:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-c", _PY_HARNESS], input=payload, capture_output=True, text=True,
                timeout=timeout_s, cwd=cwd, env={"PYTHONHASHSEED": "0"}, preexec_fn=_limits,
            )
        except subprocess.TimeoutExpired:
            res.error, res.message = "TIMEOUT", "Превышено общее время выполнения"
            return res
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        res.error, res.message = "RUNTIME_ERROR", "Процесс завершился аварийно (лимиты памяти/времени?)"
        return res
    if "fatal" in data:
        res.error, res.message = data["fatal"], data.get("msg", "")
        return res
    for t, r in zip(tests, data.get("results", [])):
        ok = bool(r.get("ok")) and _json_equal(r.get("out"), t["expected"])
        res.passed += int(ok)
        res.details.append({"ok": ok, "error": r.get("err")})
    if len(res.details) < len(tests):  # процесс оборвался посреди тестов
        res.details += [{"ok": False, "error": "NOT_RUN"}] * (len(tests) - len(res.details))
    return res


# ----------------------------------------------------------------------------- Java

@lru_cache(maxsize=1)
def java_available() -> bool:
    exe = shutil.which("java")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "--list-modules"], capture_output=True, text=True, timeout=15).stdout
        return "jdk.compiler" in out
    except Exception:
        return False


_IMPORT_RE = re.compile(r"^\s*import\s+[\w.*]+\s*;\s*$", re.M)
_JAVA_BANNED = ("System.exit", "Runtime.getRuntime", "ProcessBuilder", "java.io.File", "java.nio.file",
                "java.net", "Thread.sleep(", "System.setSecurityManager", "reflect", "sun.misc", "ClassLoader")


def build_java_main(candidate_code: str, tests: list[dict], nonce: str, result_format: str) -> str:
    imports = _IMPORT_RE.findall(candidate_code)
    body = _IMPORT_RE.sub("", candidate_code)
    lines = []
    for i, t in enumerate(tests):
        call = f"Solution.solve({', '.join(t['java_args'])})"
        fmt = f"java.util.Arrays.deepToString({call})" if result_format == "deep" else f"String.valueOf({call})"
        lines.append(
            f'        try {{ System.out.println("{nonce}_{i}:" + {fmt}); }} '
            f'catch (Throwable e) {{ System.out.println("{nonce}_{i}:ERR " + e.getClass().getSimpleName()); }}'
        )
    return "\n".join(imports) + "\npublic class Main {\n    public static void main(String[] args) {\n" + \
        "\n".join(lines) + "\n    }\n}\n" + body


def run_java_function(code: str, tests: list[dict], *, result_format: str = "scalar",
                      timeout_s: float = 25.0) -> CodeRunResult:
    res = CodeRunResult(total=len(tests))
    if not java_available():
        res.error, res.message = "JAVA_UNAVAILABLE", "JDK недоступен на сервере"
        return res
    if len(code) > 20_000 or any(b in code for b in _JAVA_BANNED):
        res.error, res.message = "FORBIDDEN_OR_INVALID", "Код содержит запрещённые конструкции"
        return res
    if not re.search(r"\bclass\s+Solution\b", code):
        res.error, res.message = "NO_ENTRYPOINT", "Нужен класс Solution с методом solve"
        return res
    nonce = "R" + secrets.token_hex(6)
    src = build_java_main(code, tests, nonce, result_format)
    with tempfile.TemporaryDirectory() as cwd:
        path = os.path.join(cwd, "Main.java")
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            proc = subprocess.run(
                [shutil.which("java"), "-Xmx128m", "-Xss512k", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", path],
                capture_output=True, text=True, timeout=timeout_s, cwd=cwd,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired:
            res.error, res.message = "TIMEOUT", "Превышено время выполнения"
            return res
    if proc.returncode != 0 and nonce not in proc.stdout:
        res.error, res.message = "COMPILE_ERROR", (proc.stderr or "")[:400]
        return res
    got: dict[int, str] = {}
    for line in proc.stdout.splitlines():
        m = re.match(rf"^{nonce}_(\d+):(.*)$", line)
        if m:
            got[int(m.group(1))] = m.group(2)
    for i, t in enumerate(tests):
        ok = got.get(i) == t["expected_str"]
        res.passed += int(ok)
        res.details.append({"ok": ok, "error": None if ok else ("ERR" if str(got.get(i, "")).startswith("ERR") else "WRONG_OR_MISSING")})
    return res
