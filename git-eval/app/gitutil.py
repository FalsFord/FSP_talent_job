"""Безопасные обёртки над git: без хуков, без интерактива, без глобального конфига."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from .config import Settings


class FetchError(RuntimeError):
    pass


def git_env(home: str, s: Settings) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home,
        "LANG": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ALLOW_PROTOCOL": "file:https" if s.allow_local else "https",
    }


def run_git(root: Path, s: Settings, *args: str, timeout: int = 60) -> str:
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.quotepath=off", "-C", str(root), *args]
    p = subprocess.run(cmd, env=git_env(str(root.parent), s), capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise FetchError(f"git {args[0]} завершился с ошибкой: {p.stderr.decode('utf-8', 'replace')[-200:]}")
    return p.stdout.decode("utf-8", "replace")


def _dir_size(path: Path) -> int:
    total = 0
    for dp, _, fns in os.walk(path):
        for f in fns:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def clone(url: str, ref: str | None, dest: Path, s: Settings) -> str:
    """Мелкий клон (depth N, без тегов и сабмодулей) с лимитами по времени и размеру. Возвращает SHA HEAD."""
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "clone", "--quiet",
           "--depth", str(s.clone_depth), "--no-tags", "--single-branch", "--no-recurse-submodules"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, str(dest)]
    limit = s.max_repo_mb * 1024 * 1024
    started = time.monotonic()
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, env=git_env(str(dest.parent), s), stdout=subprocess.DEVNULL, stderr=err)
        while proc.poll() is None:
            if time.monotonic() - started > s.clone_timeout_s:
                proc.kill()
                raise FetchError("Таймаут клонирования")
            if dest.exists() and _dir_size(dest) > limit:
                proc.kill()
                raise FetchError(f"Репозиторий больше {s.max_repo_mb} МБ")
            time.sleep(0.4)
        if proc.returncode != 0:
            err.seek(0)
            raise FetchError("Не удалось клонировать (репозиторий приватный, не существует или ветка неверна): "
                             + err.read().decode("utf-8", "replace")[-160:].strip())
    if _dir_size(dest) > limit:
        raise FetchError(f"Репозиторий больше {s.max_repo_mb} МБ")
    return run_git(dest, s, "rev-parse", "HEAD").strip()


def tracked_files(root: Path, s: Settings) -> list[str]:
    """Только файлы под контролем git; симлинки и не-обычные файлы отбрасываются (чтобы не читать за пределами клона)."""
    out = run_git(root, s, "ls-files", "-z")
    res = []
    for rel in out.split("\0"):
        if not rel:
            continue
        try:
            st = os.lstat(root / rel)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            res.append(rel)
    return res
