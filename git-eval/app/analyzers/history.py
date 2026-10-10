"""История коммитов: сколько их, насколько осмысленны сообщения, нет ли «одного гигантского коммита»."""
from __future__ import annotations

import re

from ..gitutil import run_git
from .common import Ctx, Result, clamp, finding

JUNK_MSG = {"update", "updates", "fix", "fixes", "test", "tests", "commit", "changes", "change", "wip", "asdf",
            "qwe", "final", "done", "..", ".", "stuff", "work", "upd"}
_INS = re.compile(r"(\d+) insertion")
_DEL = re.compile(r"(\d+) deletion")


def _is_junk(subject: str) -> bool:
    s = subject.strip().lower().strip(" .!")
    return len(s) < 5 or s in JUNK_MSG or bool(re.fullmatch(r"[a-z]{1,3}\d*", s))


def analyze(ctx: Ctx) -> Result:
    out = run_git(ctx.root, ctx.settings, "log", "--no-merges", "--shortstat",
                  "--format=%x1e%H%x1f%an%x1f%ae%x1f%at%x1f%s")
    commits = []
    for rec in out.split("\x1e")[1:]:
        head, _, rest = rec.partition("\n")
        h = head.split("\x1f")
        if len(h) < 5:
            continue
        ins = sum(int(x) for x in _INS.findall(rest))
        dele = sum(int(x) for x in _DEL.findall(rest))
        commits.append({"author": h[1], "email": h[2], "ts": int(h[3]), "subject": h[4], "lines": ins + dele})
    n = len(commits)
    if n == 0:
        return Result("history", None, {}, [finding("warn", "no_history", "История коммитов недоступна")])

    f: list[dict] = []
    flags: list[str] = []
    authors = {c["email"] or c["author"] for c in commits}
    span_days = (max(c["ts"] for c in commits) - min(c["ts"] for c in commits)) / 86400
    junk_share = sum(_is_junk(c["subject"]) for c in commits) / n
    total_lines = sum(c["lines"] for c in commits) or 1
    biggest = max(c["lines"] for c in commits) / total_lines

    count_s = 1.0 if n >= 5 else 0.7 if n >= 3 else 0.4 if n == 2 else 0.1
    msg_s = 1 - junk_share
    dist_s = (1.0 if biggest <= 0.6 else 0.5 if biggest <= 0.85 else 0.1) if n > 1 else 0.3
    span_s = 1.0 if (n >= 3 and span_days >= 1) else 0.5
    score = 0.35 * count_s + 0.30 * msg_s + 0.25 * dist_s + 0.10 * span_s

    if n == 1:
        f.append(finding("warn", "single_commit", "Весь проект загружен одним коммитом — процесс разработки не виден"))
        flags.append("single_commit")
    elif biggest > 0.85:
        f.append(finding("warn", "giant_commit", f"{round(biggest * 100)}% изменённых строк пришлось на один коммит"))
    if junk_share > 0.5 and n > 1:
        f.append(finding("warn", "junk_messages", f"{round(junk_share * 100)}% сообщений коммитов бессодержательны"))
    if n >= ctx.settings.clone_depth:
        f.append(finding("info", "history_truncated", f"Учтены последние {ctx.settings.clone_depth} коммитов"))

    metrics = {"commits": n, "authors": len(authors), "span_days": round(span_days, 1),
               "junk_message_share": round(junk_share, 2), "biggest_commit_share": round(biggest, 2)}

    if ctx.expected_author:
        needle = ctx.expected_author.lower()
        share = sum(needle in f"{c['author']} {c['email']}".lower() for c in commits) / n
        metrics["author_match_share"] = round(share, 2)
        if share < 0.5:
            f.append(finding("bad", "author_mismatch",
                             f"Менее половины коммитов ({round(share * 100)}%) подписаны ожидаемым автором"))
            flags.append("author_mismatch")
    metrics["flags"] = flags
    return Result("history", round(clamp(score), 3), metrics, f)
