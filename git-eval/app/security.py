"""Проверка входных URL (SSRF) и HMAC-подпись вебхуков."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import socket
import time
from urllib.parse import urlsplit

from .config import Settings


class UrlRejected(ValueError):
    pass


_PATH_RE = re.compile(r"^/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+){1,4}/?$")      # owner/repo, до 4 уровней (подгруппы GitLab)
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def validate_ref(ref: str | None) -> str | None:
    if ref is None or ref == "":
        return None
    if not _REF_RE.match(ref) or ".." in ref or ref.endswith(".lock"):
        raise UrlRejected("Недопустимое имя ветки/тега")
    return ref


def _check_public(host: str) -> None:
    """Хост должен резолвиться только в публичные адреса.
    Это не полная защита от DNS-rebinding — ограничьте исходящий трафик контейнера на уровне сети."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UrlRejected(f"Не удалось разрешить хост {host}") from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise UrlRejected("Хост указывает на непубличный адрес")


def validate_repo_url(url: str, s: Settings) -> str:
    url = (url or "").strip()
    if not url or len(url) > 300:
        raise UrlRejected("Пустой или слишком длинный URL")
    parts = urlsplit(url)
    if parts.scheme == "file" and s.allow_local:
        return url
    if parts.scheme != "https":
        raise UrlRejected("Разрешён только https")
    if parts.username or parts.password:
        raise UrlRejected("Учётные данные в URL запрещены")
    if parts.port not in (None, 443):
        raise UrlRejected("Нестандартный порт запрещён")
    host = (parts.hostname or "").lower()
    if host not in s.allowed_hosts:
        raise UrlRejected(f"Хост {host or '?'} не в списке разрешённых")
    if parts.query or parts.fragment or not _PATH_RE.match(parts.path):
        raise UrlRejected("URL должен иметь вид https://host/owner/repo")
    _check_public(host)
    return f"https://{host}{parts.path.rstrip('/')}"


def validate_callback(url: str | None, s: Settings) -> str | None:
    if not url:
        return None
    if not any(url.startswith(p) for p in s.callback_prefixes):
        raise UrlRejected("callback_url не входит в список разрешённых (GITEVAL_CALLBACK_PREFIXES)")
    return url


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str, max_age_s: int = 300) -> bool:
    try:
        if abs(time.time() - int(timestamp)) > max_age_s:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)
