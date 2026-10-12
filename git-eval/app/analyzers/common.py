from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..config import Settings

LANG_BY_EXT = {
    ".py": "python", ".java": "java", ".kt": "kotlin", ".go": "go", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".sql": "sql", ".cs": "csharp", ".rb": "ruby", ".rs": "rust",
    ".php": "php", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".swift": "swift", ".scala": "scala",
}
_TEST_NAME = re.compile(r"(^test_.*\.py$|_test\.(py|go)$|Tests?\.(java|kt|cs)$|IT\.java$|\.(spec|test)\.(js|jsx|ts|tsx)$)")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}


def lang_of(rel: str) -> str | None:
    return LANG_BY_EXT.get(PurePosixPath(rel).suffix.lower())


def is_test(rel: str) -> bool:
    p = PurePosixPath(rel)
    return bool(_TEST_NAME.search(p.name)) or any(part.lower() in _TEST_DIRS for part in p.parts[:-1])


def finding(severity: str, code: str, text: str) -> dict:
    """severity: info | warn | bad"""
    return {"severity": severity, "code": code, "text": text}


@dataclass
class Result:
    name: str
    score: float | None                 # None — анализатор неприменим и не участвует в итоговой оценке
    metrics: dict = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)


@dataclass
class Ctx:
    root: Path
    files: list[str]
    language: str | None
    rubric: list[dict]
    expected_author: str | None
    settings: Settings
    _cache: dict = field(default_factory=dict)

    def text(self, rel: str, limit: int = 300_000) -> str:
        if rel in self._cache:
            return self._cache[rel]
        p = self.root / rel
        try:
            if p.stat().st_size > limit:
                data = ""
            else:
                raw = p.read_bytes()
                data = "" if b"\0" in raw[:4096] else raw.decode("utf-8", "replace")
        except OSError:
            data = ""
        self._cache[rel] = data
        return data

    @property
    def source_files(self) -> list[str]:
        return [f for f in self.files if lang_of(f) and not is_test(f)]

    @property
    def test_files(self) -> list[str]:
        return [f for f in self.files if lang_of(f) and is_test(f)]

    def loc(self, rel: str) -> int:
        return sum(1 for line in self.text(rel).splitlines() if line.strip())

    def languages(self) -> Counter:
        c: Counter = Counter()
        for f in self.files:
            lg = lang_of(f)
            if lg:
                c[lg] += self.loc(f)
        return c


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def wavg(pairs: list[tuple[float, float]]) -> float:
    """Взвешенное среднее списка (значение, вес)."""
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else 0.0
