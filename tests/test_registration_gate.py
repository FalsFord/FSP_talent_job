"""Incomplete accounts cannot apply; introductory test score does not gate registration."""
import test_git_rewards as base
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.endpoint import EndpointState
from app.models.assessment import AssessmentSession, SessionStatus, SessionType
from app.models.reference import Grade, Specialization
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy, Application
from app.models.platform import ContactReveal


def verify():
 with TestClient(app, headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):
   assert r.status_code==status,(r.status_code,r.text[:800]);return r.json()
  registered=ok(client.post('/api/auth/register',json={'email':'registration-gate@example.org','password':'LongPassword123!','role':'candidate','consent_personal_data':True,'name':'Applicant'}))
  headers={'Authorization':'Bearer '+registered['access_token']};uid=base.UUID(registered['user']['id'])
  async def seed():
   async with SessionLocal() as db:
    c=await db.scalar(select(CandidateProfile).where(CandidateProfile.user_id==uid))
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    v=Vacancy(employer_id=ep.id,title='Registration fixture',description='Registration gate fixture',salary_min=100000,salary_max=200000,is_active=True);db.add(v)
    db.add(EndpointState(user_id=uid,key='profile',data={'complete':True,'consent':False}))
    await db.commit();return str(c.id),str(v.id)
  cid,vid=client.portal.call(seed)
  profile=ok(client.get('/api/workspace',headers=headers))['profile']
  assert profile['complete'] is False and profile['registration']['complete'] is False
  messages=' '.join(i['message'] for i in profile['registration']['issues'])
  for expected in ['фамилию','телефон','город','роль','технологию','согласие','вводный тест']:
   assert expected in messages,(expected,messages)
  with patch('app.services.ats_service.evaluate_application',new_callable=AsyncMock) as evaluate:
   blocked=ok(client.post('/api/v1/vacancies/'+vid+'/apply',headers=headers,json={}),409)
   assert blocked['code']=='REGISTRATION_INCOMPLETE' and 'завершите регистрацию' in blocked['detail']
   evaluate.assert_not_awaited()
  ok(client.post('/api/me/registration/complete',headers=headers),409)
  ok(client.put('/api/me/profile',headers=headers,json={'complete':True}),409)
  async def no_side_effects():
   async with SessionLocal() as db:
    assert not await db.scalar(select(func.count()).select_from(Application).where(Application.candidate_id==base.UUID(cid)))
    assert not await db.scalar(select(func.count()).select_from(ContactReveal).where(ContactReveal.candidate_id==base.UUID(cid)))
    assert (await db.get(CandidateProfile,base.UUID(cid))).onboarding_completed is False
  client.portal.call(no_side_effects)
  saved=ok(client.put('/api/me/profile',headers=headers,json={'name':'Applicant','surname':'Fixture','phone':'79990000000','city':'Москва','role':'Backend-разработчик','tech':['Python'],'consent':True}))
  assert saved['registration']['issues']==[{'message':'Завершите вводный тест и отправьте ответы','url':'/candidate/test'}]
  ok(client.post('/api/me/registration/complete',headers=headers),409)
  async def submit_intro():
   async with SessionLocal() as db:
    grade=await db.scalar(select(Grade));spec=await db.scalar(select(Specialization))
    db.add(AssessmentSession(candidate_id=base.UUID(cid),session_type=SessionType.onboarding,purpose='onboarding',status=SessionStatus.submitted,declared_grade_id=grade.id,specialization_id=spec.id,question_ids=[],submitted_at=datetime.now(timezone.utc),passed=False,result='fail',score=0))
    await db.commit()
  client.portal.call(submit_intro)
  ready=ok(client.get('/api/workspace',headers=headers))['profile']['registration']
  assert ready=={'complete':False,'can_complete':True,'issues':[]}
  finished=ok(client.post('/api/me/registration/complete',headers=headers))
  assert finished['complete'] is True and finished['registration']['complete'] is True
  assert finished['grade']=='Не подтверждён'
  ok(client.post('/api/me/registration/complete',headers=headers))
  with patch('app.services.ats_service.evaluate_application',new_callable=AsyncMock) as evaluate:
   ok(client.post('/api/v1/vacancies/'+vid+'/apply',headers=headers,json={}),201)
   evaluate.assert_awaited_once()
  ok(client.post('/api/v1/vacancies/'+vid+'/apply',headers=headers,json={}),409)
  assert len(ok(client.get('/api/v1/vacancies/applications/mine',headers=headers)))==1
  print('PASS canonical registration status, actionable missing steps, incomplete apply denied without side effects, completion bypass denied, failed introductory test permits completion, confirmed grade unaffected, completed apply succeeds once')


if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
