import test_git_rewards as base
from fastapi.testclient import TestClient
from unittest.mock import patch
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy,Application
from app.models.platform import TaskAssignment
from uuid import UUID
from app.api.endpoint import save

def verify():
 calls=[]
 async def evaluation(**kwargs):calls.append(kwargs);return 'queued',None
 with patch('app.api.v1.tasks.git_eval_client.submit_evaluation',evaluation),TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:500]);return r.json()
  def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
  owner=login('employer@demo.local');candidate=login('candidate@demo.local')
  async def seed():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'));c=await db.scalar(select(CandidateProfile).join(User).where(User.email=='candidate@demo.local'))
    v=Vacancy(employer_id=ep.id,title='Project fixture',description='Git project submission',salary_min=1,salary_max=2,is_active=True);db.add(v);await db.flush();db.add(Application(candidate_id=c.id,vacancy_id=v.id));await save(db,ep.user_id,'settings',{'active_vacancy_id':str(v.id)});await db.commit();return str(v.id),str(c.id)
  vid,cid=client.portal.call(seed)
  import io
  from PIL import Image
  image=io.BytesIO();Image.new('RGB',(8,8),'purple').save(image,format='PNG')
  logo=ok(client.post('/api/me/files/logo',headers=owner,files={'file':('logo.png',image.getvalue(),'image/png')}))['logo']
  assert client.get(logo,headers=candidate).status_code==200

  ok(client.put('/api/me/tasks',headers=owner,json=[{'id':1,'title':'Build an API','condition':'Implement a documented API with tests','purpose':'hiring','kind':'Отбор кандидата','language':'python','time':'20','criteria':'API works'}]))
  offer=ok(client.post('/api/vacancies/'+vid+'/assessment-invitations',headers=owner,json={'candidate_id':cid}))
  ok(client.post('/api/offers/'+offer['id']+'/assignment/start',headers=candidate))
  def finish(link):return client.put('/api/me/assessments/assignment',headers=candidate,json={'offerId':offer['id'],'done':True,'index':0,'answers':{'0':link}})
  ok(finish('https://github.com.evil.test/owner/repo'),422);assert not calls
  ok(finish('github.com/a/b/tree/main'))
  assert len(calls)==1 and calls[0]['repo_url']=='https://github.com/a/b' and calls[0]['ref']=='main'
  report=ok(client.get('/api/employer/submissions',headers=owner))[0]
  assert report['tasks'][0]['answer']=='https://github.com/a/b' and report['tasks'][0]['status']=='evaluating'
  ok(finish('github.com/a/b/tree/main'),409);assert len(calls)==1
  async def mark_failed():
   async with SessionLocal() as db:
    assignment=await db.get(TaskAssignment,UUID(report['tasks'][0]['assignment_id']))
    assignment.status='submitted';assignment.auto_score=0.2
    assignment.eval_details={'score':0.2,'summary':['Tests are missing'],'breakdown':{}}
    await db.commit()
  client.portal.call(mark_failed)
  reports=ok(client.get('/api/employer/submissions',headers=owner))
  failed=next(item for item in reports if item['id']==offer['id'])
  assert failed['completed']==0 and failed['pending']==0
  assert failed['tasks'][0]['answer']=='https://github.com/a/b'
  assert failed['tasks'][0]['git_report']['score']==0.2
  endpoint='/api/employer/submissions/'+offer['id']+'/reviewed'
  ok(client.post(endpoint,headers=candidate),403)
  marked=ok(client.post(endpoint,headers=owner));assert marked['review_status']=='reviewed'
  assert ok(client.post(endpoint,headers=owner))['reviewed_at']==marked['reviewed_at']
  assert ok(client.get('/api/employer/submissions',headers=owner))[0]['review_status']=='reviewed'
  ok(client.post('/api/v1/invitations/'+offer['id']+'/withdraw',headers=owner))
  assert ok(client.get('/api/employer/submissions',headers=owner))==[]
  ok(client.delete('/api/me/vacancies/'+vid,headers=owner))
  async def check_archive():
   from app.models.vacancy import ArchivedVacancy
   async with SessionLocal() as db:
    archived=await db.get(ArchivedVacancy,UUID(vid))
    assert archived.snapshot['vacancy']['logo']==logo
    assert archived.snapshot['applications']
    assert await db.get(Vacancy,UUID(vid)) is None
  client.portal.call(check_archive)
  workspace=ok(client.get('/api/workspace',headers=candidate))
  archived_offer=next(o for o in workspace['offers'] if o['id']==offer['id'])
  assert archived_offer['company'] and archived_offer['logo']==logo
  assert client.get(logo,headers=candidate).status_code==200



 print('PASS project repository attachment, branch forwarded to Git evaluator, invalid host rejected, single submission')

if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
