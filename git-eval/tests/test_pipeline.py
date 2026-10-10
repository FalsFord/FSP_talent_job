import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ["GITEVAL_ALLOW_LOCAL"] = "1"

from app import security                      # noqa: E402
from app.config import get_settings            # noqa: E402
from app.gitutil import FetchError             # noqa: E402
from app.pipeline import evaluate              # noqa: E402

GOOD_SRC = '''"""Сервис платежей."""


def make_key(order_id: str) -> str:
    """Ключ идемпотентности: uuid от номера заказа."""
    return f"idempotency:{order_id}"


def save(store: dict, key: str, result: dict) -> dict:
    """Сохраняем результат по ключу (redis в проде)."""
    store.setdefault(key, result)
    return store[key]
'''
GOOD_TEST = '''from app import make_key, save


def test_key():
    assert make_key("1") == "idempotency:1"


def test_save_once():
    s = {}
    save(s, "k", {"a": 1})
    save(s, "k", {"a": 2})
    assert s["k"] == {"a": 1}
'''


def sh(cwd, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Ivan Petrov", "GIT_AUTHOR_EMAIL": "ivan@example.com",
           "GIT_COMMITTER_NAME": "Ivan Petrov", "GIT_COMMITTER_EMAIL": "ivan@example.com"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def make_repo(root: Path, files_per_commit: list[tuple[str, dict]]) -> str:
    root.mkdir(parents=True)
    sh(root, "init", "-q", "-b", "main")
    for i, (msg, files) in enumerate(files_per_commit):
        for name, content in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        sh(root, "add", "-A")
        sh(root, "commit", "-q", "-m", msg, date=f"2026-01-0{i + 1}T10:00:00")
    return "file://" + str(root)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="geval_test_"))
        self.s = get_settings()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_eval(self, url, **kw):
        w = self.tmp / "work"
        w.mkdir(exist_ok=True)
        return evaluate({"repo_url": url, **kw}, w, self.s)

    def test_good_repo_scores_high(self):
        url = make_repo(self.tmp / "good", [
            ("Add project skeleton with README and gitignore", {"README.md": "# Payments\n" + "Идемпотентный POST /payments. " * 25, ".gitignore": "__pycache__/\n.env\n", "requirements.txt": "pytest\n"}),
            ("Implement idempotency key generation", {"app.py": GOOD_SRC.split("def save")[0]}),
            ("Implement result storage by key", {"app.py": GOOD_SRC}),
            ("Add unit tests for key and storage", {"tests/test_app.py": GOOD_TEST}),
            ("Add CI workflow running pytest", {".github/workflows/ci.yml": "name: ci\non: push\n"}),
        ])
        res = self.run_eval(url, rubric=[{"point": "Ключ", "keywords": ["idempotency", "uuid"]},
                                         {"point": "Хранение", "keywords": ["redis", "unique"]}],
                            expected_author="ivan")
        self.assertGreaterEqual(res["score"], 0.7, res["summary"])
        self.assertEqual(res["verdict"] in ("strong", "acceptable"), True)
        self.assertNotIn("single_commit", res["flags"])
        self.assertEqual(res["breakdown"]["rubric"]["score"], 1.0)
        self.assertEqual(res["breakdown"]["history"]["metrics"]["commits"], 5)
        self.assertAlmostEqual(sum(b["weight"] for b in res["breakdown"].values()), 1.0, places=2)

    def test_bad_repo_scores_low_and_flags(self):
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        url = make_repo(self.tmp / "bad", [
            ("update", {"main.py": f'KEY = "{fake_key}"\ndef f(:\n  pass\n', ".env": "X=1\n"}),
        ])
        res = self.run_eval(url, expected_author="somebody-else")
        self.assertLess(res["score"], 0.45, res)
        for fl in ("single_commit", "secrets_committed", "author_mismatch"):
            self.assertIn(fl, res["flags"])
        self.assertNotIn(fake_key, str(res))             # значение секрета не утекает в результат

    def test_no_source_is_capped(self):
        url = make_repo(self.tmp / "docs", [("Add docs only", {"README.md": "hello " * 200})])
        res = self.run_eval(url)
        self.assertIn("no_source_code", res["flags"])
        self.assertLessEqual(res["score"], 0.2)

    def test_missing_repo_raises(self):
        with self.assertRaises(FetchError):
            self.run_eval("file://" + str(self.tmp / "nope"))

    def test_rubric_none_is_not_counted(self):
        url = make_repo(self.tmp / "r", [("Add module with code", {"a.py": GOOD_SRC})])
        res = self.run_eval(url)
        self.assertIsNone(res["breakdown"]["rubric"]["score"])
        self.assertEqual(res["breakdown"]["rubric"]["weight"], 0)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        os.environ["GITEVAL_ALLOW_LOCAL"] = "0"
        self.s = get_settings()

    def tearDown(self):
        os.environ["GITEVAL_ALLOW_LOCAL"] = "1"

    def test_rejects_bad_urls(self):
        bad = ["http://github.com/a/b", "https://evil.com/a/b", "https://user:pw@github.com/a/b",
               "https://github.com:8443/a/b", "https://github.com/a", "https://github.com/a/b?x=1",
               "file:///etc/passwd", "git@github.com:a/b.git", "https://github.com/a/b/../../c"]
        for u in bad:
            with self.assertRaises(security.UrlRejected, msg=u):
                security.validate_repo_url(u, self.s)

    def test_accepts_public_github(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("140.82.121.3", 443))]):
            self.assertEqual(security.validate_repo_url("https://GitHub.com/octo/repo/", self.s), "https://github.com/octo/repo")

    def test_rejects_private_resolution(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(security.UrlRejected):
                security.validate_repo_url("https://github.com/octo/repo", self.s)

    def test_ref_validation(self):
        self.assertEqual(security.validate_ref("feature/x-1"), "feature/x-1")
        for r in ("--upload-pack=evil", "-x", "a..b", "a b", "x;y"):
            with self.assertRaises(security.UrlRejected, msg=r):
                security.validate_ref(r)

    def test_webhook_signature(self):
        ts = str(int(time.time()))
        sig = security.sign("sec", ts, b'{"a":1}')
        self.assertTrue(security.verify("sec", ts, b'{"a":1}', sig))
        self.assertFalse(security.verify("sec", ts, b'{"a":2}', sig))
        self.assertFalse(security.verify("other", ts, b'{"a":1}', sig))
        self.assertFalse(security.verify("sec", str(int(time.time()) - 1000), b'{"a":1}',
                                         security.sign("sec", str(int(time.time()) - 1000), b'{"a":1}')))



class WorkerStoreTests(unittest.TestCase):
    """Очередь + воркер на реальном репозитории (без HTTP: callback не задан)."""

    def test_worker_runs_and_stores(self):
        from app.store import Store
        from app.worker import Worker
        tmp = Path(tempfile.mkdtemp(prefix="geval_w_"))
        try:
            url = make_repo(tmp / "r", [("Add module with code", {"a.py": GOOD_SRC})])
            store = Store(str(tmp / "db.sqlite3"))
            s = get_settings()
            req = {"external_id": "assign-1", "repo_url": url, "ref": None}
            eid = store.create(req, url, None, None)
            self.assertEqual(store.find("assign-1", url, None)["id"], eid)
            w = Worker(store, s)
            w.enqueue(eid)
            w.pool.shutdown(wait=True)
            row = store.get(eid)
            self.assertEqual(row["status"], "done", row)
            self.assertIn("score", row["result"])

            bad = store.create({"external_id": "assign-2", "repo_url": "file:///nonexistent", "ref": None},
                               "file:///nonexistent", None, None)
            w2 = Worker(store, s)
            w2.enqueue(bad)
            w2.pool.shutdown(wait=True)
            self.assertEqual(store.get(bad)["status"], "failed")
            self.assertEqual(store.get(bad)["error"]["code"], "fetch_failed")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
