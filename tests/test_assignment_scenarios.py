"""Independent DB: versions, progress isolation, skipped tasks, technical Git failures and diversity."""
import test_git_rewards as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.employer import EmployerProfile
from app.models.candidate import CandidateProfile
from app.models.vacancy import Vacancy
from app.models.invitation import Invitation,InvitationStatus
from app.models.platform import EmployerTask,TaskAssignment
from app.api.endpoint import save,state
from app.services import git_eval_client

def verify():
 calls=[]
 async def queue(**kwargs):calls.append(kwargs);return 'unavailable','Fixture offline'
 git_eval_client.submit_evaluation=queue
 with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:800]);return r.json()
  def auth(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
  employer=auth('employer@demo.local');candidate=auth('candidate@demo.local')
  async def seed():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    c=await db.scalar(select(CandidateProfile).join(User).where(User.email=='candidate@demo.local'))
    fixtures=[]
    for i in range(2):
     v=Vacancy(employer_id=ep.id,title='Vacancy '+str(i),description='Original requirement',skills=['Python'],salary_min=1,salary_max=2,is_active=True);db.add(v);await db.flush()
     inv=Invitation(employer_id=ep.id,candidate_id=c.id,vacancy_id=v.id,title=v.title,message='Invitation',salary_min=1,salary_max=2,status=InvitationStatus.accepted);db.add(inv);await db.flush()
     tasks=[]
     for n,purpose in enumerate(('practice','hiring','hiring')):
      row=EmployerTask(employer_id=ep.id,title='Original '+str(n),statement='Original immutable condition',language='python',rubric=[{'point':'Original criterion','keywords':['original'],'weight':1}]);db.add(row);await db.flush()
      tasks.append({'id':n+1,'task_id':str(row.id),'title':row.title,'condition':row.statement,'criteria':'Original criterion','purpose':purpose,'time':'1','language':'python',**({'practice_id':'sum'} if purpose=='practice' else {})})
     await save(db,ep.user_id,'taskset:'+str(v.id),{'tasks':tasks})
     fixtures.append((str(inv.id),str(v.id),tasks))
    await db.commit();return fixtures,str(c.id),c.user_id
  fixtures,cid,cuid=client.portal.call(seed)
  for iid,vid,tasks in fixtures:ok(client.post('/api/vacancies/'+vid+'/assessment-invitations',headers=employer,json={'candidate_id':cid}))
  a,b=fixtures[0][0],fixtures[1][0]
  start=lambda iid:ok(client.post('/api/offers/'+iid+'/assignment/start',headers=candidate))
  clock=start(a);code='print(sum(map(int,input().split())))'
  body={'offerId':a,'answers':{'0':code},'index':0,'done':False}
  ok(client.put('/api/me/assessments/assignment',headers=candidate,json=body))
  async def proof():
   async with SessionLocal() as db:
    await save(db,cuid,'practice:offer:'+a+':1',{'source_code':code,'result':{'passed':1,'total':1,'solved':True,'time':.02,'memory':3000}})
    for t in fixtures[0][2]:
     row=await db.get(EmployerTask,base.UUID(t['task_id']));row.language='java';row.rubric=[{'point':'Changed','keywords':['changed']}];row.statement='CHANGED condition'
    await db.commit()
  client.portal.call(proof)
  start(b)
  ok(client.put('/api/me/assessments/assignment',headers=candidate,json={**body,'offerId':b,'done':True}),422)
  restored=start(a);assert restored['answers']['0']==code and restored['startedAt']==clock['startedAt'] and restored['checks']['0']['solved']
  ok(client.put('/api/me/assessments/assignment',headers=candidate,json={**body,'answers':{'0':code,'1':'https://github.com/example/project'},'done':True}))
  assert len(calls)==1 and calls[0]['language']=='python' and calls[0]['rubric'][0]['point']=='Original criterion'
  async def inspect():
   async with SessionLocal() as db:
    ids=[base.UUID(t['task_id']) for t in fixtures[0][2]]
    rows=(await db.execute(select(TaskAssignment).where(TaskAssignment.candidate_id==base.UUID(cid),TaskAssignment.task_id.in_(ids)))).scalars().all()
    assert len(rows)==2 and all(str(row.task_id)!=fixtures[0][2][2]['task_id'] for row in rows)
  client.portal.call(inspect)
  reports=ok(client.get('/api/employer/submissions',headers=employer));report=next(r for r in reports if r['id']==a)
  assert report['completed']==1 and report['pending']==2 and report['tasks'][1]['evaluation_status']=='unavailable',report
  assignments=ok(client.get('/api/v1/candidates/me/tasks',headers=candidate));assert all(t['vacancy_id']==fixtures[0][1] and t['statement']=='Original immutable condition' for t in assignments)
  async def old_ghost():
   async with SessionLocal() as db:
    row=TaskAssignment(task_id=base.UUID(fixtures[0][2][2]['task_id']),candidate_id=base.UUID(cid));db.add(row);await db.commit();return str(row.id)
  ghost=client.portal.call(old_ghost)
  legacy=ok(client.get('/api/v1/candidates/me/tasks',headers=candidate))
  assert next(t for t in legacy if t['id']==ghost)['status']=='skipped'
  native=next(t for t in assignments if t['purpose']=='hiring');assert native['evaluation_status']=='unavailable'
  ok(client.patch('/api/v1/employers/tasks/assignments/'+native['id'],headers=employer,json={'score':.8}))
  reviewed=ok(client.get('/api/v1/candidates/me/tasks',headers=candidate))
  assert next(t for t in reviewed if t['id']==native['id'])['evaluation_status']=='passed'
  print('PASS progress isolation, restored proof, frozen Git rubric/language, skipped task absent, exact vacancy, technical failure status')
if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
