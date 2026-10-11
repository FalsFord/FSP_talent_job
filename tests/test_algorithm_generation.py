"""Corpus rotation, model/reference validation, private daily tests, and cache stability."""
import test_git_rewards as base
import base64,json
from unittest.mock import patch
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy
from app.api.endpoint import save
from app.services import algorithm_generation as generation, knowledge_service as ks


def verify():
 counter=0; invalid=False; fail_provider=False; queued={}; prompts=[]
 cases=[{'input':s,'output':str(sum(int(x)<0 for x in s.split())),'size':len(s.split())} for s in ['', '-1','1 2','-1 -2','0 -4 7','-1 1 -2 2 0','-3 0 0 5 -8 -9']]
 class Model:
  async def complete_json(self,system,user):
   nonlocal counter
   if fail_provider:
    from app.tasks.rag.gigachat import GigaChatError
    raise GigaChatError('GigaChat отклонил генерацию из-за лимита (429)')
   counter+=1;prompt=json.JSONDecoder().raw_decode(user)[0];prompts.append(prompt)
   assert 'reference_material' in prompt and 'avoid_titles' in prompt
   def lines(c):return {'input_lines':c['input'].splitlines(),'output_lines':c['output'].splitlines(),'size':c['size']}
   return {'title':'Отрицательные значения '+str(counter),'statement':'Прочитайте целые числа из стандартного ввода, разделённые пробелами. Выведите количество отрицательных чисел. Пустой ввод даёт 0. До 10000 чисел.','topic':'Массивы','hint':'Сравните каждый элемент с нулём и сохраняйте счётчик.','examples':[lines(dict(cases[1],output='BAD') if invalid else cases[1]),lines(cases[5])],'tests':[lines(dict(c,output='MODEL_GUESSED_WRONG')) for c in cases],
    'reference_lines':['import sys','print(sum(int(x)<0 for x in sys.stdin.read().split()))']}
 async def judge(path,method='GET',body=None):
  if method=='POST':
   assert body['enable_network'] is False and body['memory_limit']==128000 and body['cpu_time_limit']==2
   token=str(len(queued));queued[token]=body;return {'token':token}
  body=queued[path.split('/')[2].split('?')[0]];stdin=base64.b64decode(body['stdin']).decode()
  answer=str(sum(int(x)<0 for x in stdin.split()))
  return {'status':{'id':3},'stdout':base64.b64encode(answer.encode()).decode(),'time':'.02','memory':4000}
 async def seed():
  async with SessionLocal() as db:
   for i in range(6):
    await ks.upsert_document(db,source='algorithm-briefs',path='https://fixture.example.org/algorithm/'+str(i),title='Corpus algorithm '+str(i),text='Алгоритмы: массивы, строки, графы, отрицательные числа '+str(i),languages=['python'],grade_hint='junior',topics=['algorithm','ready'],company=None,license_='test')
    await ks.upsert_document(db,source='algorithm-solutions',path='https://fixture.example.org/algorithm/'+str(i)+'#python-solution',title='Reference '+str(i),text='Private original reference material',languages=['python'],grade_hint='junior',topics=['algorithm','solution'],company=None,license_='test')
   ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
   v=Vacancy(employer_id=ep.id,title='Algorithms',description='Algorithm generation fixture',skills=['Python'],salary_min=1,salary_max=2,is_active=True);db.add(v);await db.flush()
   await save(db,ep.user_id,'settings',{'active_vacancy_id':str(v.id)});await db.commit()
 with patch.object(generation,'get_llm',return_value=Model()),patch('app.api.endpoint.judge',judge),patch('app.api.practice.judge',judge):
  with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
   def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:800]);return r.json()
   def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
   owner=login('employer@demo.local');candidate=login('candidate@demo.local');client.portal.call(seed)
   def create(**extra):return client.post('/api/me/tasks/generate',headers=owner,json={'purpose':'practice','language':'python','grade':'junior',**extra})
   first=ok(create())[0];second=ok(create())[1]
   assert first['template_source']!=second['template_source'] and first['practice_id']!=second['practice_id']
   assert first['validation']['status']=='passed' and 'reference_code' not in first
   assert all(t['output']!='MODEL_GUESSED_WRONG' for t in json.loads(first['tests_json']))
   regenerated=ok(create(replace_id=first['id']))[0];assert regenerated['title']!=first['title']
   invalid=True;ok(create(),503)
   assert len(ok(client.get('/api/workspace',headers=owner))['tasks'])==2
   invalid=False
   # Model selection is an explicit dependency; daily algorithms preserve existing IDs/checks.
   tasks=ok(client.get('/api/practice',headers=candidate));assert len(tasks)==4
   count=counter;assert tasks==ok(client.get('/api/practice',headers=candidate)) and counter==count
   assert all(not any(k in t for k in ['tests_json','reference_code','condition','template_source']) for t in tasks)
   checked=ok(client.post('/api/practice/'+tasks[0]['id']+'/check',headers=candidate,json={'source_code':'import sys\nprint(sum(int(x)<0 for x in sys.stdin.read().split()))','language_id':71}))
   assert checked['solved'] and checked['total']==len(cases)
   assert checked['reward']['earned']==10
   assert all('Private original reference material' in p['reference_material'] for p in prompts)
   async def older_daily():
    from app.services.reward_service import today
    async with SessionLocal() as db:
     u=await db.scalar(select(User).where(User.email=='candidate@demo.local'))
     await save(db,u.id,'practice:daily:'+today().isoformat(),[{'id':'legacy-daily','kind':'sum','parameter':2,'seed':1,'title':'Сохранённая задача','statement':'Сумма чисел','example':{'input':'2 4','output':'6'},'sources':[],'tests_json':'PRIVATE','generation_method':'retrieval_templates'}]);await db.commit()
   client.portal.call(older_daily);fail_provider=True
   preserved=ok(client.get('/api/practice',headers=candidate))
   assert preserved[0]['id']=='legacy-daily' and '429' in preserved[0]['generation_notice'] and 'tests_json' not in preserved[0]
 print('PASS model generates algorithms from rotating corpus, reference execution validation, invalid drafts rejected without saving, regeneration differs, private daily tests, cached daily catalog, editor checks and rewards')


if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
