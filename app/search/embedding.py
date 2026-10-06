import hashlib
import math
import re

from app.core.config import settings


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+#.]+", text)
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    return tokens + bigrams


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """Deterministic lightweight embedding (multilingual char n-grams via hashing)."""
    dim = dim or settings.embedding_dim
    vec = [0.0] * dim
    if not text or not text.strip():
        return vec
    for token in _tokenize(text):
        h = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(0, min(len(h), 16), 2):
            idx = int.from_bytes(h[i : i + 2], "big") % dim
            sign = 1.0 if h[i] % 2 == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def build_candidate_search_text(profile, skills: list[str], grade_name: str | None, spec_name: str | None) -> str:
    parts = [
        profile.headline or "",
        profile.about or "",
        spec_name or "",
        grade_name or "",
        " ".join(skills),
        profile.city or "",
    ]
    return " ".join(p for p in parts if p).strip()
