"""Детерминированные подсиды: один seed попытки порождает независимые потоки для каждого задания."""
from __future__ import annotations

import hashlib
import random


def sub_seed(seed: int, *parts: object) -> int:
    raw = "|".join([str(seed), *[str(p) for p in parts]])
    return int.from_bytes(hashlib.sha256(raw.encode("utf-8")).digest()[:8], "big")


def rng_for(seed: int, *parts: object) -> random.Random:
    return random.Random(sub_seed(seed, *parts))
