"""Настройки читаются из переменных окружения при каждом вызове get_settings() (удобно для тестов)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip())


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    api_key: str                        # общий секрет «основной бэк -> git-eval»
    webhook_secret: str                 # секрет подписи «git-eval -> основной бэк»
    allowed_hosts: tuple[str, ...]      # с каких хостингов разрешено клонировать
    callback_prefixes: tuple[str, ...]  # куда разрешено слать вебхук (защита от SSRF)
    db_path: str
    max_repo_mb: int
    clone_timeout_s: int
    clone_depth: int
    workers: int
    sandbox_enabled: bool               # запуск тестов кандидата в контейнере (по умолчанию ВЫКЛ)
    sandbox_image: str
    sandbox_timeout_s: int
    allow_local: bool                   # file:// URL — только для тестов


def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("GITEVAL_API_KEY", ""),
        webhook_secret=os.getenv("GITEVAL_WEBHOOK_SECRET", ""),
        allowed_hosts=_csv("GITEVAL_ALLOWED_HOSTS", "github.com,gitlab.com,bitbucket.org"),
        callback_prefixes=tuple(x.strip() for x in os.getenv("GITEVAL_CALLBACK_PREFIXES", "").split(",") if x.strip()),
        db_path=os.getenv("GITEVAL_DB_PATH", "/data/git_eval.sqlite3"),
        max_repo_mb=int(os.getenv("GITEVAL_MAX_REPO_MB", "100")),
        clone_timeout_s=int(os.getenv("GITEVAL_CLONE_TIMEOUT_S", "120")),
        clone_depth=int(os.getenv("GITEVAL_CLONE_DEPTH", "300")),
        workers=int(os.getenv("GITEVAL_WORKERS", "2")),
        sandbox_enabled=_bool("GITEVAL_SANDBOX_ENABLED", False),
        sandbox_image=os.getenv("GITEVAL_SANDBOX_IMAGE", "git-eval-sandbox:py"),
        sandbox_timeout_s=int(os.getenv("GITEVAL_SANDBOX_TIMEOUT_S", "60")),
        allow_local=_bool("GITEVAL_ALLOW_LOCAL", False),
    )
