"""Безопасное выполнение SELECT-запросов кандидата в изолированной SQLite в памяти.

Защита: authorizer разрешает только чтение (SELECT/READ/FUNCTION/RECURSIVE), запрещены PRAGMA, ATTACH, DDL, DML;
один оператор; лимит времени (progress handler); лимит длины значений; лимит строк результата.
"""
from __future__ import annotations

import math
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any


class SqlRunError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message or code


@dataclass
class SqlResult:
    columns: list[str]
    rows: list[list[Any]]


_DENIED_FUNCS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


def _authorizer(action, arg1, arg2, dbname, source):  # noqa: ANN001
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        name = (arg2 or arg1 or "").lower()
        return sqlite3.SQLITE_DENY if name in _DENIED_FUNCS else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def load_dataset(conn: sqlite3.Connection, dataset: dict) -> None:
    conn.executescript(dataset["ddl"])
    for table, spec in dataset["tables"].items():
        cols = ", ".join(spec["columns"])
        marks = ", ".join("?" for _ in spec["columns"])
        conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", spec["rows"])
    conn.commit()


def run_select(dataset: dict, query: str, *, timeout_s: float = 2.0, max_rows: int = 2000) -> SqlResult:
    q = (query or "").strip().rstrip(";").strip()
    if not q:
        raise SqlRunError("EMPTY_QUERY", "Пустой запрос")
    if not re.match(r"(?is)^(select|with)\b", q):
        raise SqlRunError("ONLY_SELECT", "Разрешён только SELECT (или WITH … SELECT)")
    conn = sqlite3.connect(":memory:")
    try:
        load_dataset(conn, dataset)  # данные загружаем ДО включения authorizer
        try:
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000)
        except (AttributeError, sqlite3.Error):
            pass
        conn.set_authorizer(_authorizer)
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
        cur = conn.execute(q)
        columns = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchmany(max_rows + 1)]
        if len(rows) > max_rows:
            raise SqlRunError("TOO_MANY_ROWS", f"Результат длиннее {max_rows} строк")
        return SqlResult(columns, rows)
    except SqlRunError:
        raise
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "interrupted" in msg:
            raise SqlRunError("TIMEOUT", "Запрос выполняется слишком долго") from e
        raise SqlRunError("SQL_ERROR", msg) from e
    except sqlite3.Error as e:
        raise SqlRunError("SQL_ERROR", str(e)) from e
    finally:
        conn.close()


def _norm_cell(v: Any) -> Any:
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        v = round(v, 2)
        return int(v) if float(v).is_integer() else v
    if isinstance(v, bytes):
        return v.hex()
    return v


def _row_key(row: list[Any]) -> tuple:
    return tuple(_norm_cell(c) for c in row)


def compare_results(expected: list[list[Any]], got: list[list[Any]], *, ordered: bool) -> bool:
    """Сравнение по значениям и порядку столбцов (названия столбцов не важны)."""
    if len(expected) != len(got):
        return False
    e = [_row_key(r) for r in expected]
    g = [_row_key(r) for r in got]
    if e and g and len(e[0]) != len(g[0]):
        return False
    if ordered:
        return e == g
    return Counter(map(repr, e)) == Counter(map(repr, g))
