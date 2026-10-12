"""Second chances preserve old solutions and create independent candidate attempts."""
import test_git_rewards as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy, Application
from app.api.endpoint import save, state


def verify():
 with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:800]);return r.json() if status!=204 else None
  def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
  owner=login('employer@demo.local');candidate=login('candidate@demo.local')
  async def seed():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    c=await db.scalar(select(CandidateProfile).join(User).where(User.email=='candidate@demo.local'))
    v=Vacancy(employer_id=ep.id,title='Retry algorithms',description='Independent algorithm attempts fixture',salary_min=100000,salary_max=200000,is_active=True);db.add(v);await db.flush()
    application=Application(vacancy_id=v.id,candidate_id=c.id);db.add(application);await db.flush()
    await save(db,ep.user_id,'settings',{'active_vacancy_id':str(v.id)});await db.commit()
    await save(db,ep.user_id,'ats:application:'+str(application.id),{'state':'pending','category':'review'});await db.commit()
    return str(c.id),str(v.id),str(c.user_id),str(application.id)
  cid,vid,uid,application_id=client.portal.call(seed)
  conversation_url='/api/v1/vacancies/applications/'+application_id+'/conversation'
  ok(client.post(conversation_url,headers=owner),409)
  ok(client.patch('/api/v1/vacancies/applications/'+application_id,headers=owner,json={'status':'accepted'}))
  conversation=ok(client.post(conversation_url,headers=owner))
  assert ok(client.post(conversation_url,headers=owner))==conversation
  listed=ok(client.get('/api/v1/vacancies/'+vid+'/applications',headers=owner))
  assert listed[0]['offer_id']==conversation['offer_id'] and listed[0]['offer_status']=='sent'
  ok(client.post('/api/offers/'+conversation['offer_id']+'/stage',headers=owner,json={'stage':'Знакомство','message':'Отклик принят, приглашаем обсудить команду.'}))
  task={'id':1,'title':'Reverse sequence','condition':'Read numbers and print them in reverse order.','practice_id':'reverse','purpose':'practice','kind':'Алгоритм','time':'20','language':'python'}
  original=ok(client.put('/api/me/tasks',headers=owner,json=[task]))[0]
  send='/api/vacancies/'+vid+'/assessment-invitations'
  first=ok(client.post(send,headers=owner,json={'candidate_id':cid}));assert first['assessment_attempt']==1 and first['assessment_created']
  assert first['id']==conversation['offer_id']
  duplicate=ok(client.post(send,headers=owner,json={'candidate_id':cid}));assert duplicate['id']==first['id'] and not duplicate['assessment_created']
  initial_clock=ok(client.post('/api/offers/'+first['id']+'/assignment/start',headers=candidate))
  stage_url='/api/offers/'+first['id']+'/stage'
  stage_body={'stage':'Техническое собеседование','message':'Давайте согласуем время встречи.'}
  ok(client.post(stage_url,headers=owner,json=stage_body),409)
  ok(client.post(stage_url,headers=candidate,json=stage_body),403)
  code1='print(" ".join(input().split()[::-1]))'
  async def proof(offer,code):
   async with SessionLocal() as db:
    await save(db,base.UUID(uid),'practice:offer:'+offer+':1',{'source_code':code,'language_id':71,'result':{'solved':True,'passed':4,'total':4}});await db.commit()
  client.portal.call(proof,first['id'],code1)
  finish=lambda offer,code:client.put('/api/me/assessments/assignment',headers=candidate,json={'offerId':offer,'done':True,'index':0,'answers':{'0':code}})
  ok(finish(first['id'],code1))
  stage=ok(client.post(stage_url,headers=owner,json=stage_body))
  assert stage['name']==stage_body['stage'] and len(stage['history'])==2
  assert ok(client.post(stage_url,headers=owner,json=stage_body))==stage
  chat=ok(client.get('/api/offers/'+first['id']+'/messages',headers=candidate))
  assert len(chat)==3 and stage_body['message'] in chat[-1]['text'] and not chat[-1]['mine']
  assert any(n['type']=='hiring_stage' for n in ok(client.get('/api/v1/notifications',headers=candidate))['items'])
  assert next(o for o in ok(client.get('/api/workspace',headers=candidate))['offers'] if o['id']==first['id'])['hiring_stage']['name']==stage_body['stage']
  second=ok(client.post(send,headers=owner,json={'candidate_id':cid}))
  assert second['id']!=first['id'] and second['previous_offer_id']==first['id'] and second['assessment_attempt']==2
  assert second['tasks'][0]['task_id']!=original['task_id']
  ws=ok(client.get('/api/workspace',headers=candidate));by_id={o['id']:o for o in ws['offers']}
  assert by_id[first['id']]['assessment_submitted'] and not by_id[second['id']]['assessment_submitted']
  assert 'tests_json' not in by_id[second['id']]['tasks'][0]
  second_clock=ok(client.post('/api/offers/'+second['id']+'/assignment/start',headers=candidate))
  assert second_clock['answers']=={} and not second_clock['done'] and second_clock['offerId']==second['id']
  code2=code1+'\n# Second independent solution'
  ok(finish(second['id'],code2),422)
  client.portal.call(proof,second['id'],code2);ok(finish(second['id'],code2));ok(finish(second['id'],code2),409)
  old=ok(client.get('/api/offers/'+first['id']+'/assignment',headers=candidate))
  assert old['answers']['0']==code1 and old['deadlineAt']==initial_clock['deadlineAt']
  reports=ok(client.get('/api/employer/submissions',headers=owner))
  first_report=next(r for r in reports if r['id']==first['id']);second_report=next(r for r in reports if r['id']==second['id'])
  assert first_report['tasks'][0]['answer']==code1 and second_report['tasks'][0]['answer']==code2
  assert first_report['tasks'][0]['assignment_id']!=second_report['tasks'][0]['assignment_id']
  assert first_report['hiring_stage']['name']==stage_body['stage'] and first_report['offer_id']==first['id']
  ok(client.post('/api/v1/invitations/'+first['id']+'/withdraw',headers=candidate),403)
  ok(client.post('/api/v1/invitations/'+first['id']+'/withdraw',headers=owner))
  ok(client.post('/api/v1/invitations/'+first['id']+'/withdraw',headers=owner))
  ok(client.post(stage_url,headers=owner,json=stage_body),409)
  assert len(ok(client.get('/api/offers/'+first['id']+'/messages',headers=candidate)))==4
  ok(client.post('/api/offers/'+first['id']+'/assignment/start',headers=candidate),409)
  third=ok(client.post(send,headers=owner,json={'candidate_id':cid}));assert third['assessment_attempt']==3
  ok(client.post('/api/offers/'+third['id']+'/assignment/start',headers=candidate))
  async def expire():
   async with SessionLocal() as db:
    key='assessment:offer:'+third['id'];value=await state(db,base.UUID(uid),key)
    await save(db,base.UUID(uid),key,{**value,'deadlineAt':1});await db.commit()
  client.portal.call(expire)
  fourth=ok(client.post(send,headers=owner,json={'candidate_id':cid}));assert fourth['assessment_attempt']==4
  assert ok(client.get('/api/offers/'+third['id']+'/assignment',headers=candidate))['result']['status']=='expired'
  notification=ok(client.get('/api/v1/notifications',headers=candidate))
  assert any(n['payload'].get('offer_id')==fourth['id'] for n in notification['items'])
  ok(client.post('/api/v1/invitations/'+fourth['id']+'/withdraw',headers=owner))
  fifth=ok(client.post(send,headers=owner,json={'candidate_id':cid}));assert fifth['assessment_attempt']==5
  # Deleting a conversation only clears the requesting participant's history.
  chat_url='/api/offers/'+first['id']+'/chat'
  peer_history=ok(client.get('/api/offers/'+first['id']+'/messages',headers=candidate))
  ok(client.request('DELETE',chat_url,headers=owner))
  assert ok(client.get('/api/offers/'+first['id']+'/messages',headers=owner))==[]
  assert ok(client.get('/api/offers/'+first['id']+'/messages',headers=candidate))==peer_history
  assert first['id'] in ok(client.get('/api/workspace',headers=owner))['hidden_chat_ids']
  ok(client.post(chat_url+'/restore',headers=owner))
  assert first['id'] not in ok(client.get('/api/workspace',headers=owner))['hidden_chat_ids']
  assert ok(client.get('/api/offers/'+first['id']+'/messages',headers=owner))==[]
  notifications=ok(client.get('/api/v1/notifications',headers=candidate))['items'];nid=notifications[0]['id']
  ok(client.request('DELETE','/api/v1/notifications/'+nid,headers=owner),404)
  ok(client.request('DELETE','/api/v1/notifications/'+nid,headers=candidate),204)
  assert all(n['id']!=nid for n in ok(client.get('/api/v1/notifications',headers=candidate))['items'])
  ok(client.request('DELETE','/api/v1/notifications',headers=candidate),204)
  assert ok(client.get('/api/v1/notifications',headers=candidate))['unread']==0
  ok(client.request('DELETE','/api/me/vacancies/'+vid,headers=candidate),403)
  ok(client.request('DELETE','/api/me/vacancies/'+vid,headers=owner))
  assert all(v['id']!=vid for v in ok(client.get('/api/workspace',headers=owner))['vacancies'])
  preserved=ok(client.get('/api/employer/submissions',headers=owner));assert any(r['id']==first['id'] for r in preserved)
  assert next(o for o in ok(client.get('/api/workspace',headers=candidate))['offers'] if o['id']==fifth['id'])['native_status']=='withdrawn'
  ok(client.request('DELETE','/api/me/account',headers=candidate,json={'password':'wrong'}),403)
  ok(client.request('DELETE','/api/me/account',headers=candidate,json={'password':'demo1234'}))
  ok(client.get('/api/workspace',headers=candidate),401)
  ok(client.post('/api/auth/login',json={'email':'candidate@demo.local','password':'demo1234'}),401)
  async def last_vacancy():
   async with SessionLocal() as db:
    ep=await db.scalar(select(EmployerProfile).join(User).where(User.email=='employer@demo.local'))
    row=Vacancy(employer_id=ep.id,title='Account deletion fixture',description='Must be unpublished when employer account is deleted',salary_min=1,salary_max=2,is_active=True);db.add(row);await db.commit();return row.id
  last_id=client.portal.call(last_vacancy)
  ok(client.request('DELETE','/api/me/account',headers=owner,json={'password':'demo1234'}))
  ok(client.get('/api/workspace',headers=owner),401)
  async def check_unpublished():
   async with SessionLocal() as db:assert not (await db.get(Vacancy,last_id)).is_active
  client.portal.call(check_unpublished)
  print('PASS deletion: private chat history, notification ownership and counters, vacancy cleanup preserves reports, account password and token revocation')
  print('PASS second chance appears with notification, active sends do not duplicate, fresh timer and checks, old solutions immutable, separate reports, retry after timeout')


if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
