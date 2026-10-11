"""Isolated DB: applicant profiles remain accessible without making them publicly searchable."""
import test_git_rewards as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy,Application,ApplicationStatus
from app.models.platform import ContactReveal
from app.models.invitation import Invitation,InvitationStatus

def verify():
 with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:500]);return r.json()
  def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
  owner=login('employer@demo.local');candidate=login('candidate@demo.local')
  registered=ok(client.post('/api/auth/register',json={'email':'profile-unrelated@example.org','password':'LongPassword123!','role':'employer','consent_personal_data':True,'name':'Other employer'}))
  other={'Authorization':'Bearer '+registered['access_token']}
  async def seed():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    c=await db.scalar(select(CandidateProfile).join(User).where(User.email=='candidate@demo.local'))
    c.onboarding_completed=False;c.is_discoverable=True
    v=Vacancy(employer_id=ep.id,title='Profile fixture',description='Applicant access fixture',skills=['Python'],salary_min=100000,salary_max=200000,is_active=True);db.add(v);await db.flush()
    application=Application(vacancy_id=v.id,candidate_id=c.id,status=ApplicationStatus.accepted);db.add(application);await db.flush()
    db.add(ContactReveal(candidate_id=c.id,employer_id=ep.id,source='application',source_id=application.id))
    await db.commit();return str(c.id),str(ep.id),registered['user']['id'],str(v.id)
  cid,eid,other_uid,vid=client.portal.call(seed)
  url='/api/candidates/'+cid;preview='/api/v1/employers/candidates/'+cid+'/preview'
  assert ok(client.get(url,headers=owner))['id']==cid
  assert ok(client.get(preview,headers=owner))['contacts_hidden'] is False
  ok(client.get(url,headers=other),404);ok(client.get(preview,headers=other),404)
  ok(client.get(url,headers=candidate),403)
  assert all(p['id']!=cid for p in ok(client.get('/api/workspace',headers=owner))['people'])
  proposal={'candidate_id':cid,'title':'Profile fixture','message':'Invitation access fixture','salary_min':100000,'salary_max':200000}
  denied=ok(client.post('/api/v1/invitations',headers=other,json=proposal),404)
  assert 'не откликался' in str(denied)
  invitation=ok(client.post('/api/offers',headers=owner,json={'candidate_id':cid,'vacancy_id':vid}))
  assert invitation['status']=='new' and invitation['native_status']=='sent'
  assert any(i['id']==invitation['id'] for i in ok(client.get('/api/v1/invitations/received',headers=candidate)))
  ok(client.post('/api/v1/invitations/'+invitation['id']+'/withdraw',headers=owner))
  async def change(hidden,complete,contacts):
   async with SessionLocal() as db:
    c=await db.get(CandidateProfile,base.UUID(cid));c.is_discoverable=not hidden;c.onboarding_completed=complete;c.privacy={**(c.privacy or {}),'show_contacts_after_accept':contacts};await db.commit()
  client.portal.call(change,True,False,False)
  private=ok(client.get(url,headers=owner));assert 'email' not in private and 'phone' not in private
  assert ok(client.get(preview,headers=owner))['contacts_hidden'] is True
  ok(client.get(url,headers=other),404)
  hidden_invitation=ok(client.post('/api/v1/invitations',headers=owner,json={**proposal,'vacancy_id':vid}),201)
  assert hidden_invitation['status']=='sent' and not hidden_invitation.get('candidate_contacts')
  # Retries must retain the normal cooldown instead of creating duplicate invitations.
  ok(client.post('/api/v1/invitations',headers=owner,json={**proposal,'vacancy_id':vid}),409)
  async def invite():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).where(EmployerProfile.user_id==base.UUID(other_uid)))
    db.add(Invitation(employer_id=ep.id,candidate_id=base.UUID(cid),title='Profile invitation',message='Existing contact',salary_min=100000,salary_max=200000,status=InvitationStatus.sent));await db.commit()
  client.portal.call(invite)
  assert ok(client.get(url,headers=other))['id']==cid
  assert ok(client.get(preview,headers=other))['contacts_hidden'] is True
  client.portal.call(change,False,True,True)
  assert any(p['id']==cid for p in ok(client.get('/api/workspace',headers=owner))['people'])
  ok(client.get('/api/candidates/'+str(base.uuid4()),headers=owner),404)
  print('PASS incomplete/hidden applicant profile and invitation access, candidate receives invitation, unrelated employer denied, contact privacy retained, invitation cooldown, discovery rules unchanged')
if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
