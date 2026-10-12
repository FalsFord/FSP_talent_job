"""One live draft, read-only corpus lookup; no employer/candidate data writes."""
import asyncio
from app.db.session import SessionLocal
from app.services.algorithm_generation import generate

async def main():
 async with SessionLocal() as db:
  result=await generate(db,context='Массивы и строки: ежедневная практика для начинающего разработчика',grade='junior')
  assert result['validation']['status']=='passed'
  print({'title':result['title'],'generation_method':result['generation_method'],'source':result['template_source'],'validated_tests':result['validation']['tests']})

if __name__=='__main__':asyncio.run(main())
