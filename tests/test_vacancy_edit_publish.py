"""Disposable database regression for editing, targeted saving and actual publication."""
import test_git_rewards as base
from fastapi.testclient import TestClient
from app.main import app

def verify():
 with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
  def ok(r,status=200):
   assert r.status_code==status,(r.status_code,r.text[:600])
   return r.json()
  def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
  employer=login('employer@demo.local');candidate=login('candidate@demo.local')
  first=ok(client.post('/api/vacancies',headers=employer))['id']
  valid={'id':first,'title':'Python Developer','tasks':'Build services and maintain tested REST APIs','salaryMin':'120 000','salaryMax':'180000','tech':['Python'],'company':'Fixture company','consent':True,'published':False}
  saved=ok(client.put('/api/me/vacancy',headers=employer,json=valid));assert not saved['published']
  assert not any(v['id']==first for v in ok(client.get('/api/v1/vacancies')))
  pub=ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':first}));assert pub['published']
  assert any(v['id']==first for v in ok(client.get('/api/v1/vacancies')))
  # Partial edits of an existing published vacancy are not blocked by incomplete legacy fields.
  edited=ok(client.put('/api/me/vacancy',headers=employer,json={**valid,'title':'Updated Python role','tasks':'short','salaryMin':'','published':True}))
  assert edited['published'] and edited['title']=='Updated Python role' and edited['tasks']=='short'
  error=ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':first}),422)
  assert 'Задачи и обязанности' in error['detail'] and 'Зарплата «от»' in error['detail']
  second=ok(client.post('/api/vacancies',headers=employer))['id']
  # A delayed autosave explicitly addressed to first must not overwrite selected second.
  fixed=ok(client.put('/api/me/vacancy',headers=employer,json={'id':first,'tasks':valid['tasks'],'salaryMin':'130000','published':True}))
  assert fixed['salaryMax']=='180000' and fixed['tech']==['Python'] and fixed['title']=='Updated Python role'
  ws=ok(client.get('/api/workspace',headers=employer));assert ws['vacancy']['id']==second and not ws['vacancy']['published']
  ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':first}))
  # Draft failures stay drafts; they do not alter company data or create another vacancy.
  bad={**valid,'id':second,'title':'New role','tasks':'','salaryMin':'0','company':'Must not save on rejected publication','published':True}
  ok(client.put('/api/me/vacancy',headers=employer,json=bad),422)
  ws=ok(client.get('/api/workspace',headers=employer));assert ws['vacancy']['company']=='Fixture company' and not ws['vacancy']['published']
  ready={**valid,'id':second,'title':'New Python vacancy','consent':False}
  ok(client.put('/api/me/vacancy',headers=employer,json=ready))
  ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':second}),422)
  ok(client.put('/api/me/vacancy',headers=employer,json={'id':second,'consent':True}))
  ok(client.post('/api/me/vacancy/publish',headers=candidate,json={'id':second}),403)
  ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':str(base.uuid4())}),404)
  for _ in range(2):assert ok(client.post('/api/me/vacancy/publish',headers=employer,json={'id':second}))['published']
  ws=ok(client.get('/api/workspace',headers=employer));assert ws['vacancy']['id']==second and ws['vacancy']['published']
  assert ws['vacancy']['tasks']==valid['tasks'] and len([v for v in ws['vacancies'] if v['id'] in (first,second)])==2
  print('PASS published editing, incomplete drafts, clear validation, actual publication, repeated publication, exact vacancy saving, consent/ownership and atomic failures')

if __name__=='__main__':
 base.asyncio.run(base.database(True))
 try:
  base.subprocess.run([base.sys.executable,'-m','app.db.init_db'],check=True);base.subprocess.run([base.sys.executable,'-m','app.db.seed'],check=True);verify()
 finally:base.asyncio.run(base.database(False))
