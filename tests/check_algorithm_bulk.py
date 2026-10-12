"""Audit imported 200-task corpus, source attribution, deduplication, answer separation."""
import asyncio
import json
from collections import Counter
from pathlib import Path
from sqlalchemy import select,func
from app.db.session import SessionLocal
from app.models.tasks import KnowledgeDocument
from app.services.algorithm_bulk_import import ingest
from app.services.knowledge_service import retrieve_context

async def main():
    root=Path('/corpus')
    records=json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    counts=Counter(r['source_repo'] for r in records)
    assert counts=={'neetcode':100,'exercism':60,'thealgorithms':40}
    assert len({r['url'] for r in records})==200
    assert all(r['code'].strip() and r['brief'].strip() and r['sha256'] and r['solution_url'] for r in records)
    async with SessionLocal() as db:
        result=await ingest(db,root)
        assert result['import']=={'created':0,'updated':0,'unchanged':400},result
        for source in ('algorithm-briefs','algorithm-solutions'):
            n=await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.source==source))
            assert n==200,(source,n)
        ctx=await retrieve_context(db,query='array stack algorithm string',language='python',grade='junior',pool=100,k=20)
        assert ctx.chunks and all(not c['label'].startswith('algorithm-solutions:') for c in ctx.chunks)
    size=sum(p.stat().st_size for p in root.iterdir() if p.is_file())
    print(json.dumps({'status':'PASS','tasks':200,'solutions':200,'sources':counts,'archive_bytes':size,'reimport':'400 unchanged','answers_excluded':True}))

asyncio.run(main())
