"""Разбор Markdown-документов корпуса и нарезка на чанки для retrieval."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass
class ParsedDoc:
    title: str
    text: str
    content_hash: str


def clean_markdown(raw: str) -> str:
    t = raw.replace("\r\n", "\n")
    t = _LINK.sub(r"\1", t)                      # ссылки → текст
    t = re.sub(r"<[^>]+>", " ", t)               # html-теги
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)  # картинки
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def parse_markdown(raw: str, fallback_title: str = "") -> ParsedDoc:
    text = clean_markdown(raw)
    m = _HEADING.search(text)
    title = (m.group(2) if m else "") or fallback_title or (text.split("\n", 1)[0][:80] if text else "")
    return ParsedDoc(title=title.strip()[:200], text=text, content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())


def chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Абзацы склеиваются до max_chars; длинные абзацы режутся по предложениям; между чанками — перекрытие."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= max_chars:
            pieces.append(p)
            continue
        sent: list[str] = []
        for part in re.split(r"(?<=[.!?…])\s+", p):
            if len(part) <= max_chars:
                sent.append(part)
                continue
            words, cur_w = part.split(), ""      # предложение без знаков препинания режем по словам
            for w in words:
                if cur_w and len(cur_w) + len(w) + 1 > max_chars:
                    sent.append(cur_w)
                    cur_w = w
                else:
                    cur_w = f"{cur_w} {w}".strip()
            if cur_w:
                sent.append(cur_w)
        buf = ""
        for s in sent:
            if buf and len(buf) + len(s) + 1 > max_chars:
                pieces.append(buf)
                buf = s
            else:
                buf = f"{buf} {s}".strip()
        if buf:
            pieces.append(buf)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = f"{tail}\n\n{p}" if tail else p
        else:
            cur = f"{cur}\n\n{p}".strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if len(c) >= 40]
