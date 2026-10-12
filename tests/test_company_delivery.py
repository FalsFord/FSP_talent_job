import test_git_rewards as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy
from app.models.invitation import Invitation,InvitationStatus
from app.db.session import SessionLocal
from app.api.endpoint import save
from app.models.platform import EmployerTask

def verify():
 with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def auth(email):
   r=client.post('/api/auth/login',json={'email':email,'password':'demo1234'});assert r.status_code==200
   return {'Authorization':'Bearer '+r.json()['access_token']}
  employer=auth('employer@demo.local');candidate=auth('candidate@demo.local')
  async def seed():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    c=await db.scalar(select(CandidateProfile).join(User).where(User.email=='candidate@demo.local'))
    v=Vacancy(employer_id=ep.id,title='Delivery fixture',description='Solve a sum',skills=['Python'],salary_min=1,salary_max=2,is_active=True)
    db.add(v);await db.flush()
    inv=Invitation(employer_id=ep.id,candidate_id=c.id,vacancy_id=v.id,title=v.title,message='Invitation fixture',salary_min=1,salary_max=2,status=InvitationStatus.accepted)
    db.add(inv);await db.flush()
    task=EmployerTask(employer_id=ep.id,title='Sum algorithm',statement='Read integers and output their sum',language='python',rubric=[]);db.add(task);await db.flush()
    await save(db,ep.user_id,'taskset:'+str(v.id),{'tasks':[{'id':1,'task_id':str(task.id),'title':'Sum algorithm','condition':'Read two integers and output their sum','purpose':'practice','practice_id':'custom:fixture','tests_json':'[{"input":"2 3","output":"5"}]'}]})
    await db.commit();return str(v.id),str(c.id),str(inv.id),ep.user_id
  vid,cid,iid,euid=client.portal.call(seed)
  url='/api/vacancies/'+vid+'/assessment-invitations'
  for _ in range(2):
   r=client.post(url,headers=employer,json={'candidate_id':cid});assert r.status_code==200,r.text
  data=client.get('/api/workspace',headers=candidate).json()
  offer=next(o for o in data['offers'] if o['id']==iid)
  assert offer['tasks'][0]['title']=='Sum algorithm' and 'tests_json' not in offer['tasks'][0]
  notifications=client.get('/api/v1/notifications',headers=candidate).json()['items']
  notes=[n for n in notifications if n['type']=='company_assessment' and n['payload'].get('offer_id')==iid]
  assert len(notes)==1 and notes[0]['payload']['url']=='/candidate/tasks'
  async def edit():
   async with SessionLocal() as db:
    await save(db,euid,'taskset:'+vid,{'tasks':[]});await db.commit()
  client.portal.call(edit)
  offer=next(o for o in client.get('/api/workspace',headers=candidate).json()['offers'] if o['id']==iid)
  assert len(offer['tasks'])==1
  r=client.put('/api/me/assessments/assignment',headers=candidate,json={'offerId':iid,'startedAt':1,'answers':{},'index':0,'done':False});assert r.status_code==200,r.text
  clock=r.json();assert clock['startedAt']>1 and clock['deadlineAt']>clock['startedAt']
  code='print(sum(map(int,input().split())))'
  async def checked(passed):
   async with SessionLocal() as db:
    c=await db.get(CandidateProfile,base.UUID(cid))
    await save(db,c.user_id,'practice:offer:'+iid+':1',{'source_code':code,'result':{'passed':passed,'total':1,'time':.01,'memory':3000}});await db.commit()
  client.portal.call(checked,0)
  body={'offerId':iid,'startedAt':9999999999999,'answers':{'0':code},'index':0,'done':True}
  r=client.put('/api/me/assessments/assignment',headers=candidate,json=body);assert r.status_code==422,r.text
  client.portal.call(checked,1)
  r=client.put('/api/me/assessments/assignment',headers=candidate,json=body);assert r.status_code==200,r.text
  rows=client.get('/api/employer/submissions',headers=employer);assert rows.status_code==200,rows.text
  report=next(i for i in rows.json() if i['id']==iid);assert report['completed']==1 and report['tasks'][0]['answer']==code and report['tasks'][0]['execution']['memory']==3000
  r=client.put('/api/me/assessments/assignment',headers=candidate,json=body);assert r.status_code==409,r.text
  async def overdue():
   async with SessionLocal() as db:
    c=await db.get(CandidateProfile,base.UUID(cid))
    await save(db,c.user_id,'assessment:offer:'+iid,{'offerId':iid,'startedAt':1,'deadlineAt':2,'done':False,'answers':{}})
    await save(db,c.user_id,'assessment:assignment',{});await db.commit()
  client.portal.call(overdue)
  r=client.put('/api/me/assessments/assignment',headers=candidate,json=body);assert r.status_code==409,r.text
  rows=client.get('/api/employer/submissions',headers=employer);assert all(i['id']!=iid for i in rows.json()),rows.text
  notes=client.get('/api/v1/notifications',headers=employer).json()['items'];assert any(n['type']=='assessment_failed' for n in notes)
  print('PASS server clock, failed tests rejected, successful algorithm submission, detailed review, one-shot guard, deadline expiry, zero/expired excluded, failure notification')
if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True)
  base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True)
  verify()
 finally:base.asyncio.run(base.database(False))




