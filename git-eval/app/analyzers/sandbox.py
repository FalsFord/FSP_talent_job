"""Опциональный запуск тестов кандидата в одноразовом контейнере без сети.

ВНИМАНИЕ. Это единственное место, где исполняется чужой код. По умолчанию выключено (GITEVAL_SANDBOX_ENABLED=0).
Не включайте, пока не выполнены условия из README: отдельный хост/ВМ для воркера, образ с предустановленными
библиотеками, никакого доступа к docker.sock из публичного процесса, лимиты ядра (gVisor/Kata — лучше).
Код проверен только на уровне сборки команды; в этой среде docker не запускался.
"""
from __future__ import annotations

import re
import subprocess

from ..config import Settings

_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors)")


def build_command(root: str, s: Settings) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--network", "none",                      # без сети
        "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "256m", "--memory-swap", "256m", "--cpus", "1",
        "--user", "65534:65534",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{root}:/work:ro", "-w", "/work",
        s.sandbox_image,
        "timeout", str(s.sandbox_timeout_s), "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--maxfail=50",
    ]


def run_pytest(root: str, s: Settings) -> dict | None:
    """None — если запуск не удался технически (docker недоступен, таймаут контейнера и т.п.)."""
    try:
        p = subprocess.run(build_command(root, s), capture_output=True, timeout=s.sandbox_timeout_s + 20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = p.stdout.decode("utf-8", "replace")
    counts = {"passed": 0, "failed": 0, "error": 0}
    for n, kind in _SUMMARY.findall(out):
        counts["error" if kind.startswith("error") else kind] += int(n)
    total = sum(counts.values())
    return {**counts, "total": total, "exit_code": p.returncode, "timed_out": p.returncode == 124}
