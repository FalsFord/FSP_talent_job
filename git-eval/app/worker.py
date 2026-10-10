"""Фоновое выполнение оценок и доставка результата в основной бэкенд подписанным вебхуком."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import security
from .config import Settings
from .gitutil import FetchError
from .pipeline import EmptyRepo, evaluate
from .store import Store

log = logging.getLogger("git_eval")
RETRY_DELAYS = (1, 3, 10, 30, 90)


class Worker:
    def __init__(self, store: Store, s: Settings):
        self.store, self.s = store, s
        self.pool = ThreadPoolExecutor(max_workers=s.workers, thread_name_prefix="geval")

    def enqueue(self, eid: str) -> None:
        self.pool.submit(self._run, eid)

    def recover(self) -> None:
        """После рестарта: добить прерванные оценки и недоставленные вебхуки."""
        for eid in self.store.unfinished():
            self.enqueue(eid)
        for eid in self.store.undelivered():
            self.pool.submit(self._deliver, eid)

    def _run(self, eid: str) -> None:
        row = self.store.get(eid)
        if not row:
            return
        self.store.set_status(eid, "running")
        work = Path(tempfile.mkdtemp(prefix="geval_"))
        try:
            self.store.set_result(eid, evaluate(row["request"], work, self.s))
        except security.UrlRejected as e:
            self.store.set_error(eid, "url_rejected", str(e))
        except FetchError as e:
            self.store.set_error(eid, "fetch_failed", str(e))
        except EmptyRepo as e:
            self.store.set_error(eid, "empty_repo", str(e))
        except Exception:
            log.exception("evaluation %s crashed", eid)
            self.store.set_error(eid, "internal", "Внутренняя ошибка оценки")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self._deliver(eid)

    def _deliver(self, eid: str) -> None:
        row = self.store.get(eid)
        if not row or not row["callback_url"]:
            return
        import httpx                                    # импорт здесь: ядру оценки httpx не нужен

        body = json.dumps({"id": row["id"], "external_id": row["external_id"], "status": row["status"],
                           "result": row["result"], "error": row["error"]}, ensure_ascii=False).encode()
        for attempt, delay in enumerate((0, *RETRY_DELAYS)):
            time.sleep(delay)
            ts = str(int(time.time()))
            headers = {"Content-Type": "application/json", "X-GitEval-Timestamp": ts,
                       "X-GitEval-Signature": security.sign(self.s.webhook_secret, ts, body)}
            try:
                r = httpx.post(row["callback_url"], content=body, headers=headers, timeout=10)
                if 200 <= r.status_code < 300:
                    self.store.set_callback(eid, "ok")
                    return
                log.warning("callback %s -> HTTP %s (attempt %s)", eid, r.status_code, attempt + 1)
            except httpx.HTTPError as e:
                log.warning("callback %s failed: %s (attempt %s)", eid, e, attempt + 1)
        self.store.set_callback(eid, "failed")
