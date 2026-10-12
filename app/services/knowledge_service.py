"""RAG: загрузка корпуса (документы → чанки → эмбеддинги → pgvector) и гибридный retrieval.

Retrieval = векторный поиск (косинус, HNSW) ∪ ключевой поиск (полнотекст PostgreSQL) → слияние RRF →
учёт близости грейда → MMR для разнообразия контекста. Результат — ContextPack, который управляет выбором темы,
предметной «легенды» и архетипа задания (см. app/tasks/blueprint.py, generators)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import KnowledgeChunk, KnowledgeDocument
from app.search.embedding import embed_text, embed_texts
from app.tasks.generators import ALL_GENERATORS
from app.tasks.knowledge_builtin import BUILTIN_NOTES
from app.tasks.rag import chunking, classify, retriever
from app.tasks.types import ContextPack

log = logging.getLogger("knowledge")
HEXLET_LICENSE = "AGPL-3.0 (репозиторий Hexlet/ru-test-assignments); тексты заданий © компаний-авторов"


async def upsert_document(db: AsyncSession, *, source: str, path: str, title: str, text: str, languages: list[str],
                          grade_hint: str | None, topics: list[str], company: str | None, license_: str) -> str:
    """Возвращает 'created' | 'updated' | 'unchanged'."""
    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    res = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.source == source, KnowledgeDocument.path == path))
    doc = res.scalar_one_or_none()
    status = "created"
    if doc:
        if doc.content_hash == chash:
            return "unchanged"
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
        doc.title, doc.text, doc.content_hash = title[:256], text, chash
        doc.languages, doc.grade_hint, doc.topics, doc.company, doc.license = languages, grade_hint, topics, company, license_
        status = "updated"
    else:
        doc = KnowledgeDocument(source=source, path=path, title=title[:256], text=text, content_hash=chash,
                                languages=languages, grade_hint=grade_hint, topics=topics, company=company, license=license_)
        db.add(doc)
    await db.flush()
    pieces = chunking.chunk_text(text) or [text[:900]]
    vectors = embed_texts(pieces)
    for i, (piece, vec) in enumerate(zip(pieces, vectors)):
        db.add(KnowledgeChunk(document_id=doc.id, idx=i, text=piece, languages=languages, grade_hint=grade_hint,
                              topics=topics, embedding=vec))
    await db.flush()
    return status


async def ingest_builtin(db: AsyncSession) -> dict:
    stats = {"created": 0, "updated": 0, "unchanged": 0}
    for n in BUILTIN_NOTES:
        st = await upsert_document(db, source="builtin", path=n["path"], title=n["title"], text=n["text"],
                                   languages=n["languages"], grade_hint=n["grade"], topics=n["topics"], company=None,
                                   license_="MIT (проект)")
        stats[st] += 1
    await db.commit()
    return stats


def iter_markdown(root: Path):
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if len(rel.parts) == 1:          # README.md, CONTRIBUTING.md и т.п. в корне — не задания
            continue
        yield p, rel.as_posix()


async def ingest_directory(db: AsyncSession, root: Path, *, source: str = "hexlet-ru-test-assignments",
                           only_languages: set[str] | None = None, batch: int = 25) -> dict:
    """Загружает *.md из локальной копии корпуса (git clone). Документы без языков python/java/sql пропускаются."""
    if (root / 'prepared/assignments.jsonl').is_file():
        return await ingest_prepared(db, root)
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    only = only_languages or {"python", "java", "sql"}
    n = 0
    for path, rel in iter_markdown(root):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if len(raw) < 200:
            stats["skipped"] += 1
            continue
        parsed = chunking.parse_markdown(raw, fallback_title=path.stem)
        meta = classify.classify(rel, parsed.title, parsed.text)
        langs = [l for l in meta.languages if l in only]
        if not langs:
            stats["skipped"] += 1
            continue
        st = await upsert_document(db, source=source, path=rel, title=parsed.title, text=parsed.text, languages=langs,
                                   grade_hint=meta.grade_hint, topics=meta.topics, company=meta.company,
                                   license_=HEXLET_LICENSE)
        stats[st] += 1
        n += 1
        if n % batch == 0:
            await db.commit()
    await db.commit()
    return stats


async def ingest_prepared(db: AsyncSession, root: Path) -> dict:
    """Import only the cleaned active corpus; preserve exact supplied chunks and URLs."""
    chunks = {}
    with (root / 'prepared/rag_chunks.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            chunks.setdefault(item['assignment_id'], []).append(item)
    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0}
    with (root / 'prepared/assignments.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            if not item['generation']['eligible'] or not item['statement']['text'].strip():
                stats['skipped'] += 1
                continue
            langs = [t['name'].lower() for t in item['technologies']]
            track_lang = {'frontend': 'javascript', 'python': 'python', 'java': 'java', 'analytics': 'sql', 'go': 'go', 'php': 'php'}
            langs = sorted(set(langs + [track_lang.get(item['track'], 'python')]))
            st = await upsert_document(db, source='full_data', path=item['source']['url'], title=item['title'],
                text=item['statement']['text'], languages=langs, grade_hint=item['seniority'],
                topics=[item['track'], item['generation']['readiness'], *item['generation']['pattern_labels']],
                company=item.get('company'), license_=item['source'].get('assignment_license', 'unknown'))
            if st != 'unchanged':
                doc = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.source == 'full_data',
                    KnowledgeDocument.path == item['source']['url']))).scalar_one()
                await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
                pieces = chunks.get(item['id'], [])
                vectors = embed_texts([p['embedding_text'] for p in pieces])
                for p, vec in zip(pieces, vectors):
                    db.add(KnowledgeChunk(document_id=doc.id, idx=p['ordinal'], text=p['text'],
                        languages=langs, grade_hint=item['seniority'], topics=doc.topics, embedding=vec))
            stats[st] += 1
            if sum(stats.values()) % 25 == 0:
                await db.commit()
    await db.commit()
    return stats


async def knowledge_stats(db: AsyncSession) -> dict:
    docs = await db.execute(select(KnowledgeDocument.source, func.count()).group_by(KnowledgeDocument.source))
    chunks = await db.execute(select(func.count()).select_from(KnowledgeChunk))
    return {"documents_by_source": {s: c for s, c in docs.all()}, "chunks": chunks.scalar_one()}


def _tsquery(text: str, max_tokens: int = 12) -> str:
    toks = []
    for t in re.findall(r"[a-zа-яё0-9]{3,}", text.lower()):
        if t not in toks:
            toks.append(t)
    return " | ".join(toks[:max_tokens])


async def retrieve_context(db: AsyncSession, *, query: str, language: str, grade: str, k: int = 6,
                           pool: int = 30, include_solutions: bool = False, source_filter: list[str] | None = None) -> ContextPack:
    """Гибридный retrieval. Если корпус пуст — возвращает пустой контекст (генерация работает без RAG-подсказок)."""
    lang_filter = KnowledgeChunk.languages.contains([language])
    if source_filter:
        lang_filter = lang_filter & KnowledgeChunk.document_id.in_(select(KnowledgeDocument.id).where(KnowledgeDocument.source.in_(source_filter)))
    if not include_solutions:
        lang_filter = lang_filter & ~KnowledgeChunk.topics.contains(['solution'])
    qvec = embed_text(query, query=True)
    vec_rows = (await db.execute(
        select(KnowledgeChunk.id).where(lang_filter).order_by(KnowledgeChunk.embedding.cosine_distance(qvec)).limit(pool)
    )).scalars().all()
    kw_rows: list = []
    tsq = _tsquery(query)
    if tsq:
        tsv = func.to_tsvector("simple", KnowledgeChunk.text)
        q = func.to_tsquery("simple", tsq)
        kw_rows = (await db.execute(
            select(KnowledgeChunk.id).where(lang_filter, tsv.op("@@")(q)).order_by(func.ts_rank(tsv, q).desc()).limit(pool)
        )).scalars().all()
    fused = retriever.rrf([list(vec_rows), list(kw_rows)])
    ids = [cid for cid, _ in fused[: pool]]
    if not ids:
        return ContextPack(query=query)
    rows = (await db.execute(
        select(KnowledgeChunk, KnowledgeDocument).join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.id.in_(ids))
    )).all()
    rrf_score = dict(fused)
    top = max(rrf_score.values()) or 1.0
    cands = []
    for ch, doc in rows:
        vec = [float(x) for x in (ch.embedding if ch.embedding is not None else [])]
        label = f"{doc.source}: {doc.title}" + (f" ({doc.company})" if doc.company else "")
        base = 0.6 * (rrf_score[ch.id] / top) + 0.4 * retriever.grade_affinity(ch.grade_hint or doc.grade_hint, grade)
        cands.append({"id": str(ch.id), "vec": vec, "base": base, "text": ch.text, "label": label,
                      "url":doc.path if doc.source in ('full_data','algorithm-briefs') else None, "readiness":'partial' if 'partial' in doc.topics else 'ready'})
    picked = retriever.mmr(cands, qvec, k=k)
    gens = [g for g in ALL_GENERATORS if g.language == language]
    return retriever.build_context(query, picked, gens)
