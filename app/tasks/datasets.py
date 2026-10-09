"""Синтетические наборы данных для SQL-заданий (детерминированы по seed)."""
from __future__ import annotations

import random
from datetime import date, timedelta

NAMES = [
    "Алексей", "Мария", "Иван", "Ольга", "Дмитрий", "Анна", "Сергей", "Елена", "Павел", "Наталья",
    "Андрей", "Татьяна", "Николай", "Юлия", "Михаил", "Ирина", "Артём", "Светлана", "Кирилл", "Полина",
    "Егор", "Вера",
]
CITIES = ["Москва", "Казань", "Самара", "Омск", "Тула", "Пермь"]


def build_dataset(
    rng: random.Random,
    theme: dict,
    *,
    n_parents: int = 14,
    n_children: int = 45,
    days: int = 40,
    bursts: bool = False,
    ok_share: float = 0.6,
    bad_share: float = 0.2,
) -> dict:
    """Две связанные таблицы (parent 1—N child). Часть parent намеренно без child (для anti-join)."""
    n_parents = min(n_parents, len(NAMES))
    names = rng.sample(NAMES, n_parents)
    cities = rng.sample(CITIES, 4)
    parents = [[i + 1, names[i], rng.choice(cities)] for i in range(n_parents)]
    ids = [p[0] for p in parents]
    inactive = set(rng.sample(ids, max(1, n_parents // 5)))
    active = [i for i in ids if i not in inactive]

    start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 200))
    raw: list[tuple[str, int, int, str]] = []

    def status() -> str:
        r = rng.random()
        return theme["ok"] if r < ok_share else theme["bad"] if r < ok_share + bad_share else theme["other"]

    for _ in range(n_children):
        raw.append(((start + timedelta(days=rng.randrange(days))).isoformat(), rng.choice(active),
                    rng.randrange(100, 5000, 100), status()))
    if bursts:  # серии подряд идущих дней (для задач на «островки»)
        for pid in rng.sample(active, max(2, len(active) // 2)):
            run = rng.randint(2, 5)
            d0 = start + timedelta(days=rng.randrange(max(1, days - run)))
            for j in range(run):
                raw.append(((d0 + timedelta(days=j)).isoformat(), pid, rng.randrange(100, 5000, 100), status()))
    raw.sort(key=lambda r: r[0])
    children = [[i + 1, r[1], r[2], r[3], r[0]] for i, r in enumerate(raw)]

    p, c, fk, amt = theme["parent"], theme["child"], theme["fk"], theme["amt"]
    ddl = (
        f"CREATE TABLE {p} (id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL);"
        f"CREATE TABLE {c} (id INTEGER PRIMARY KEY, {fk} INTEGER NOT NULL, {amt} INTEGER NOT NULL, "
        f"status TEXT NOT NULL, created_at TEXT NOT NULL);"
    )
    return {
        "ddl": ddl,
        "tables": {
            p: {"columns": ["id", "name", "city"], "rows": parents},
            c: {"columns": ["id", fk, amt, "status", "created_at"], "rows": children},
        },
    }


def schema_text(theme: dict) -> str:
    p, c, fk, amt = theme["parent"], theme["child"], theme["fk"], theme["amt"]
    return (
        f"{p}(id INTEGER PK, name TEXT, city TEXT)\n"
        f"{c}(id INTEGER PK, {fk} INTEGER → {p}.id, {amt} INTEGER, status TEXT, created_at TEXT 'YYYY-MM-DD')"
    )


def preview(dataset: dict, n: int = 5) -> dict:
    return {t: {"columns": s["columns"], "rows": s["rows"][:n]} for t, s in dataset["tables"].items()}
