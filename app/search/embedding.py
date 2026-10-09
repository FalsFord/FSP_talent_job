import hashlib
import logging
import math
import re

from app.core.config import settings

log = logging.getLogger("embedding")
_FASTEMBED = None
_FASTEMBED_FAILED = False


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+#.]+", text)
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    return tokens + bigrams


def _hash_embed(text: str, dim: int) -> list[float]:
    """Детерминированный лёгкий эмбеддинг (хеширование токенов и биграмм). Не семантический: близость слов с
    разной формой он не улавливает — для production включите EMBEDDING_BACKEND=fastembed."""
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


def _fastembed_embed(texts: list[str], dim: int, query: bool) -> list[list[float]] | None:
    """Семантические эмбеддинги (ONNX, без PyTorch) через необязательный пакет fastembed."""
    global _FASTEMBED, _FASTEMBED_FAILED
    if _FASTEMBED_FAILED:
        return None
    try:
        if _FASTEMBED is None:
            from fastembed import TextEmbedding  # ленивый импорт: пакет необязателен

            _FASTEMBED = TextEmbedding(model_name=settings.embedding_model)
        prefix = ("query: " if query else "passage: ") if "e5" in settings.embedding_model.lower() else ""
        out = [[float(x) for x in v] for v in _FASTEMBED.embed([prefix + t for t in texts])]
        if out and len(out[0]) != dim:
            raise ValueError(f"размерность модели {len(out[0])} != EMBEDDING_DIM {dim}")
        return out
    except Exception as e:  # noqa: BLE001
        _FASTEMBED_FAILED = True
        log.warning("fastembed недоступен (%s) — используется hash-эмбеддинг", e)
        return None


def embed_texts(texts: list[str], dim: int | None = None, *, query: bool = False) -> list[list[float]]:
    dim = dim or settings.embedding_dim
    if settings.embedding_backend == "fastembed":
        res = _fastembed_embed(texts, dim, query)
        if res is not None:
            return res
    return [_hash_embed(t, dim) for t in texts]


def embed_text(text: str, dim: int | None = None, *, query: bool = False) -> list[float]:
    return embed_texts([text], dim, query=query)[0]


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
