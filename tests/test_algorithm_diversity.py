import test_git_rewards as base
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.services import knowledge_service as ks,algorithm_bank as bank,daily_algorithms as daily
from app.db.session import SessionLocal
from app.models.user import User
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy
from app.api.endpoint import save

def verify():
 context=SimpleNamespace(text='array list unique sum stack prefix graph bfs binary sort gcd theory frequency hash динамика динамич теория чисел массив сортиров скоб стек последователь подмассив таблиц бинар делител частот',sources=['Fixture algorithms'],chunks=[{'label':'Fixture algorithms','text':'array list unique sum stack prefix graph bfs binary sort gcd theory frequency hash динамика динамич теория чисел массив сортиров скоб стек последователь подмассив таблиц бинар делител частот'}])
 async def retrieve(*args,**kwargs):return context
 ks.retrieve_context=retrieve
 for t in bank.CATALOG:
  assert bank.oracle(t['id'],t['example']['input'])==t['example']['output'],t['id']
  cases=bank.cases(t['id']);assert any(n==10000 for _,_,n in cases)
  assert cases==bank.cases(t['id'])
 assert bank.oracle('max_subarray','-5 -2 -10')=='-2'
 assert bank.oracle('lis_length','2 2 1 3')=='2'
 assert bank.oracle('two_sum','6\n3')=='NO'
 assert bank.oracle('mixed_brackets','([)]')=='NO'
 assert bank.oracle('shortest_path','3 1\n0 1')=='-1'
 # Production generation now uses the 200-source GigaChat pipeline. Its endpoint,
 # reference validation and source rotation are covered by test_algorithm_generation.
 days=[base.asyncio.run(daily.generate(None,'2026-10-'+str(day))) for day in (11,12,13,14)]
 assert len({tuple(t['kind'] for t in tasks) for tasks in days})==4
 assert any(t['kind'].startswith('bank:') for tasks in days for t in tasks)
 print('PASS deterministic fallback catalog, daily rotation and golden edge cases')
if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
