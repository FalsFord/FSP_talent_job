"""Очередь и результаты в SQLite. Для нескольких реплик замените на Postgres/Redis (интерфейс класса не меняется)."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    external_id TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    ref TEXT,
    status TEXT NOT NULL,                -- queued | running | done | failed
    request TEXT NOT NULL,
    result TEXT,
    error TEXT,
    callback_url TEXT,
    callback_status TEXT,                -- NULL | ok | failed
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eval_ext ON evaluations(external_id, repo_url, ref);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.path = path
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        d["request"] = json.loads(d["request"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        d["error"] = json.loads(d["error"]) if d["error"] else None
        return d

    def find(self, external_id: str, repo_url: str, ref: str | None) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM evaluations WHERE external_id=? AND repo_url=? AND IFNULL(ref,'')=IFNULL(?,'') "
                          "ORDER BY created_at DESC LIMIT 1", (external_id, repo_url, ref)).fetchone()
        return self._row(r)

    def create(self, req: dict, repo_url: str, ref: str | None, callback_url: str | None) -> str:
        eid = uuid.uuid4().hex
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO evaluations (id, external_id, repo_url, ref, status, request, callback_url, created_at, updated_at)"
                      " VALUES (?,?,?,?,?,?,?,?,?)",
                      (eid, req["external_id"], repo_url, ref, "queued", json.dumps(req, ensure_ascii=False),
                       callback_url, now, now))
        return eid

    def get(self, eid: str) -> dict | None:
        with self._conn() as c:
            return self._row(c.execute("SELECT * FROM evaluations WHERE id=?", (eid,)).fetchone())

    def set_status(self, eid: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE evaluations SET status=?, updated_at=? WHERE id=?", (status, _now(), eid))

    def set_result(self, eid: str, result: dict) -> None:
        with self._conn() as c:
            c.execute("UPDATE evaluations SET status='done', result=?, error=NULL, updated_at=? WHERE id=?",
                      (json.dumps(result, ensure_ascii=False), _now(), eid))

    def set_error(self, eid: str, code: str, message: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE evaluations SET status='failed', error=?, updated_at=? WHERE id=?",
                      (json.dumps({"code": code, "message": message}, ensure_ascii=False), _now(), eid))

    def set_callback(self, eid: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE evaluations SET callback_status=?, updated_at=? WHERE id=?", (status, _now(), eid))

    def requeue(self, eid: str, req: dict, callback_url: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE evaluations SET status='queued', error=NULL, result=NULL, callback_status=NULL, request=?, "
                      "callback_url=?, updated_at=? WHERE id=?",
                      (json.dumps(req, ensure_ascii=False), callback_url, _now(), eid))

    def unfinished(self) -> list[str]:
        """Задания, прерванные рестартом, и «зависшие» доставки вебхука."""
        with self._conn() as c:
            rows = c.execute("SELECT id FROM evaluations WHERE status IN ('queued','running')").fetchall()
        return [r["id"] for r in rows]

    def undelivered(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT id FROM evaluations WHERE status IN ('done','failed') AND callback_url IS NOT NULL "
                             "AND callback_status IS NULL").fetchall()
        return [r["id"] for r in rows]
