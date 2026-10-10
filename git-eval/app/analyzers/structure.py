"""Структура репозитория: README, тесты, CI, манифест зависимостей, .gitignore, мусор в git."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from .common import Ctx, Result, finding, wavg

CI_MARKERS = (".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/", "azure-pipelines.yml", ".travis.yml")
MANIFESTS = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "pom.xml", "build.gradle",
             "build.gradle.kts", "package.json", "go.mod", "Cargo.toml", "Gemfile", "composer.json"}
JUNK = re.compile(r"(^|/)(node_modules|venv|\.venv|__pycache__|\.idea|dist|target|\.gradle)/|\.pyc$|(^|/)\.env$|\.DS_Store$|\.class$|\.jar$")


def analyze(ctx: Ctx) -> Result:
    f: list[dict] = []
    parts: list[tuple[float, float]] = []

    readme = next((x for x in ctx.files if "/" not in x and x.lower().startswith("readme")), None)
    rlen = len(ctx.text(readme).strip()) if readme else 0
    r_score = 1.0 if rlen >= 500 else 0.6 if rlen >= 150 else 0.3 if rlen > 0 else 0.0
    parts.append((r_score, 0.30))
    if not readme:
        f.append(finding("bad", "no_readme", "Нет README: непонятно, как запускать и что делает проект"))
    elif rlen < 150:
        f.append(finding("warn", "short_readme", "README почти пустой"))

    has_tests = bool(ctx.test_files)
    parts.append((1.0 if has_tests else 0.0, 0.25))
    if not has_tests:
        f.append(finding("bad", "no_tests_dir", "В репозитории не найдено файлов с тестами"))

    has_ci = any(x.startswith(m) or x == m for x in ctx.files for m in CI_MARKERS)
    parts.append((1.0 if has_ci else 0.0, 0.10))
    if not has_ci:
        f.append(finding("info", "no_ci", "Нет конфигурации CI"))

    has_manifest = any(PurePosixPath(x).name in MANIFESTS for x in ctx.files)
    parts.append((1.0 if has_manifest else 0.0, 0.15))
    if not has_manifest:
        f.append(finding("warn", "no_manifest", "Нет файла зависимостей (requirements.txt / pom.xml / package.json …)"))

    has_ignore = ".gitignore" in ctx.files
    parts.append((1.0 if has_ignore else 0.0, 0.10))

    junk = [x for x in ctx.files if JUNK.search(x)]
    parts.append((0.0 if len(junk) > 5 else 0.5 if junk else 1.0, 0.10))
    if junk:
        f.append(finding("warn", "junk_committed", f"В git попали служебные файлы (venv/.pyc/.env/…): {len(junk)} шт., например {junk[0]}"))

    big = [x for x in ctx.files if (ctx.root / x).stat().st_size > 5 * 1024 * 1024]
    if big:
        f.append(finding("warn", "big_binaries", f"Файлы крупнее 5 МБ в репозитории: {len(big)} шт."))

    return Result("structure", round(wavg(parts), 3),
                  {"files": len(ctx.files), "readme_chars": rlen, "tests_present": has_tests, "ci": has_ci,
                   "manifest": has_manifest, "junk_files": len(junk)}, f)
