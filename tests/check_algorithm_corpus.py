"""Live corpus verification: idempotent import and answer separation; no candidate writes."""
import asyncio
from pathlib import Path
from sqlalchemy import select,func
from app.db.session import SessionLocal
from app.models.tasks import KnowledgeDocument
from app.services.algorithm_import import ingest,TASKS
from app.services.knowledge_service import retrieve_context

async def main():
    async with SessionLocal() as db:
        result=await ingest(db,Path('/data/algorithms/neetcode'))
        assert result['import']=={'created':0,'updated':0,'unchanged':len(TASKS)*2},result
        for source in ('algorithm-briefs','algorithm-solutions'):
            count=await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.source==source))
            assert count==len(TASKS),(source,count)
        default=await retrieve_context(db,query='algorithm Решение array class Solution Python',language='python',grade='junior',pool=500,k=200)
        assert all(not c['label'].startswith('algorithm-solutions:') for c in default.chunks)
        private=await retrieve_context(db,query='algorithm Решение array class Solution Python',language='python',grade='junior',pool=500,k=200,include_solutions=True)
        solutions=[c for c in private.chunks if c['label'].startswith('algorithm-solutions:')]
        assert solutions,'Solution retrieval unavailable'
        assert any(c['label'].startswith('algorithm-briefs:') for c in default.chunks),'Imported topics not searchable'
        print('PASS 20 briefs + 20 solutions; duplicate-free reimport; default RAG excludes answers; private RAG accesses solutions')

asyncio.run(main())
