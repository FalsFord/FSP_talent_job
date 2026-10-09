"""Адаптер реестра ФСП. API и структура данных ФСП не предоставляются (ТЗ), поэтому интерфейс — наша гипотеза:
достижение = {title, event_name, event_date, rank, description}. В production MockFspProvider заменяется
реализацией на базе ФСП ID (Keycloak/OIDC) и REST реестра; остальной код менять не нужно."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Protocol

from app.core.config import settings


class FspProvider(Protocol):
    async def fetch_achievements(self, external_id: str) -> list[dict]: ...


_EVENTS = [
    ("Открытый кубок ФСП", "Участник командного тура"),
    ("Чемпионат ФСП по спортивному программированию", "Участник очного этапа"),
    ("Хакатон ФСП", "Участник хакатона"),
    ("Школа ФСП: алгоритмы", "Завершил программу"),
]


class MockFspProvider:
    """Детерминированные демо-данные: по external_id получается от 0 до 3 достижений — часть связанных аккаунтов
    намеренно остаётся без истории, чтобы проверять обработку этого случая."""

    async def fetch_achievements(self, external_id: str) -> list[dict]:
        h = int(hashlib.sha1(external_id.encode("utf-8")).hexdigest(), 16)
        out = []
        for i in range(h % 4):
            name, title = _EVENTS[(h >> (4 * i)) % len(_EVENTS)]
            out.append({"title": title, "event_name": name, "event_date": date(2024 + (h >> (8 + i)) % 2, 1 + (h >> (2 + i)) % 12, 10),
                        "rank": [1, 2, 3, 5, 8, 15, None][(h >> (3 * i + 5)) % 7],
                        "description": "Демо-данные (MockFspProvider)"})
        return out


def get_provider() -> FspProvider:
    if not settings.fsp_mock_mode:
        raise NotImplementedError("Реальная интеграция с ФСП ID/реестром не реализована: реализуйте FspProvider")
    return MockFspProvider()
