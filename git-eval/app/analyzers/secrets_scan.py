"""Поиск секретов в отслеживаемых файлах. Значения секретов НИКОГДА не попадают в результат — только путь и строка."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from .common import Ctx, Result, finding

PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("generic_secret", re.compile(r"""(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['"]([^'"\s]{12,})['"]""")),
]
PLACEHOLDER = re.compile(r"(?i)(change|example|your[_-]|xxx|<.+>|\$\{|placeholder|dummy|test|fake|secret_key_here|\*{3,})")
SKIP_SUFFIX = {".md", ".lock", ".svg", ".min.js"}


def analyze(ctx: Ctx) -> Result:
    hits: list[tuple[str, str, int]] = []
    for rel in ctx.files:
        name = PurePosixPath(rel).name
        if name == ".env":
            hits.append(("env_file", rel, 0))
            continue
        if PurePosixPath(rel).suffix.lower() in SKIP_SUFFIX:
            continue
        for i, line in enumerate(ctx.text(rel).splitlines(), 1):
            if len(line) > 400:
                continue
            for kind, rx in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                if kind == "generic_secret" and PLACEHOLDER.search(m.group(2)):
                    continue
                hits.append((kind, rel, i))
                break
    f = [finding("bad", "secret_committed", f"Похоже на секрет ({k}) в {p}" + (f":{ln}" if ln else "")) for k, p, ln in hits[:10]]
    critical = any(k in ("private_key", "aws_key", "github_token") for k, _, _ in hits)
    score = 1.0 if not hits else 0.0 if (critical or len(hits) >= 2) else 0.5
    return Result("secrets", score, {"hits": len(hits), "kinds": sorted({k for k, _, _ in hits})}, f)
