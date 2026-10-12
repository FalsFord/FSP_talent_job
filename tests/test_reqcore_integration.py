"""API contracts and employer isolation in a disposable DB; AI is mocked here."""
import asyncio
import os
import subprocess
import sys
from uuid import uuid4
import asyncpg
from fastapi.testclient import TestClient

original_url = os.environ['DATABASE_URL']
database = 'ats_verify_' + uuid4().hex[:12]
os.environ['DATABASE_URL'] = original_url.rsplit('/', 1)[0] + '/' + database
os.environ['BACKGROUND_JOBS_ENABLED'] = 'false'

async def database_action(create):
    conn = await asyncpg.connect(original_url.replace('postgresql+asyncpg:', 'postgresql:'))
    try:
        await conn.execute(f'CREATE DATABASE "{database}"' if create else f'DROP DATABASE "{database}" WITH (FORCE)')
    finally: await conn.close()

def verify():
    from app.main import app
    from app.services import ats_service as ats
    calls=[]
    async def fake_request(path, body):
        calls.append(path)
        if path=='/auto-config':
            return dict(mode='auto',min_grade='middle',min_experience_years=3,required_skills=['Python'],work_format='remote',salary_max=180000,weights=dict(grade=25,experience=25,skills=35,format=10,salary=5),suitable_threshold=75,unsuitable_threshold=35,strict_grade=True,strict_experience=True,reqcore_criteria=[])
        if path=='/validate-config': return body
        if path=='/generate-config': return {**await fake_request('/auto-config',body), 'source':'reqcore_ai'}
        if path=='/evaluate':
            assert 'vacancy' in body and 'candidate' in body and 'hrms' not in body
            return dict(category='unsuitable',score=20,coverage=100,criteria=[dict(key='experience',label='Опыт',requirement='3 года',evidence='<script>bad</script>',status='mismatch',strengths=[],gaps=['Недостаточно опыта'])],summary='Нужна проверка человеком',notice='Рекомендация',provider='Reqcore',model='test')
        raise AssertionError(path)
    ats.request=fake_request
    with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
        def expect(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:400])
            return r.json() if r.headers.get('content-type','').startswith('application/json') else r.text
        def login(email): return {'Authorization':'Bearer '+expect(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
        candidate=login('candidate@demo.local')
        other=login('employer@demo.local')
        owner={'Authorization':'Bearer '+expect(client.post('/api/auth/register',json={'email':'ats-owner@example.org','password':'LongPassword123!','role':'employer','consent_personal_data':True,'name':'ATS Test'}))['access_token']}
        vacancy_id=expect(client.post('/api/vacancies',headers=owner))['id']
        expect(client.put('/api/me/vacancy',headers=owner,json={'title':'Python Developer','tasks':'Разработка сервисов на FastAPI','description':'Опыт от 3 лет','company':'ATS Test','salaryMin':'120000','salaryMax':'180000','tech':['Python'],'format':'Удалённо','direction':'Backend','grade':'Middle','published':True}))
        base='/api/v1/vacancies/'+vacancy_id
        recipients='/api/vacancies/'+vacancy_id+'/assessment-recipients'
        test_invitation='/api/vacancies/'+vacancy_id+'/assessment-invitations'
        candidate_id=expect(client.get('/api/workspace',headers=candidate))['profile']['id']
        assert expect(client.get(recipients,headers=owner)) == []
        expect(client.get(recipients,headers=other),404)
        expect(client.post(test_invitation,headers=owner,json={'candidate_id':candidate_id}),403)
        settings=expect(client.get(base+'/ats/settings',headers=owner))['criteria']
        expect(client.get(base+'/ats/settings',headers=candidate),403)
        expect(client.get(base+'/ats/settings',headers=other),404)
        application=expect(client.post(base+'/apply',headers=candidate,json={'cover_letter':'Python'}),201)
        assert candidate_id in {r['id'] for r in expect(client.get(recipients,headers=owner))}
        expect(client.post(test_invitation,headers=owner,json={'candidate_id':candidate_id}),409)
        taskset=expect(client.put('/api/me/tasks',headers=owner,json=[{'id':1,'title':'Тестовое задание','condition':'Опишите реализацию API'}]))
        chat_offer=expect(client.post(test_invitation,headers=owner,json={'candidate_id':candidate_id}))
        async def seed_messages():
            from app.db.session import SessionLocal
            from app.models.invitation import Invitation
            from app.models.employer import EmployerProfile
            from app.models.endpoint import ChatMessage
            from uuid import UUID
            async with SessionLocal() as db:
                inv=await db.get(Invitation,UUID(chat_offer['id']))
                ep=await db.get(EmployerProfile,inv.employer_id)
                rows=[ChatMessage(offer_id=inv.id,sender_id=ep.user_id,text='Тестовое сообщение') for _ in range(2)]
                db.add_all(rows);await db.commit()
                return [r.id for r in rows]
        message_ids=client.portal.call(seed_messages)
        assert expect(client.get('/api/messages/unread',headers=candidate))['unread']==2
        assert expect(client.get('/api/messages/unread',headers=owner))['unread']==0
        read_url='/api/offers/'+chat_offer['id']+'/messages/read'
        expect(client.post(read_url,headers=other,json={'last_id':message_ids[-1]}),404)
        expect(client.post(read_url,headers=candidate,json={'last_id':message_ids[0]}))
        assert expect(client.get('/api/messages/unread',headers=candidate))['unread']==1
        expect(client.post(read_url,headers=candidate,json={'last_id':message_ids[-1]}))
        expect(client.post(read_url,headers=candidate,json={'last_id':message_ids[0]}))
        assert expect(client.get('/api/messages/unread',headers=candidate))['unread']==0
        maria=login('maria@demo.local')
        maria_id=expect(client.get('/api/workspace',headers=maria))['profile']['id']
        assert maria_id not in {r['id'] for r in expect(client.get(recipients,headers=owner))}
        expect(client.post('/api/offers',headers=owner,json={'vacancy_id':vacancy_id,'candidate_id':maria_id}))
        assert maria_id in {r['id'] for r in expect(client.get(recipients,headers=owner))}
        expect(client.post(test_invitation,headers=owner,json={'candidate_id':maria_id}))
        ivan=login('ivan@demo.local')
        ivan_id=expect(client.get('/api/workspace',headers=ivan))['profile']['id']
        assign_url='/api/v1/employers/tasks/'+taskset[0]['task_id']+'/assign'
        expect(client.post(assign_url,headers=owner,json={'candidate_ids':[ivan_id]}),403)
        expect(client.post(assign_url,headers=owner,json={'candidate_ids':[maria_id]}))
        second_vacancy=expect(client.post('/api/vacancies',headers=owner))['id']
        assert expect(client.get('/api/vacancies/'+second_vacancy+'/assessment-recipients',headers=owner)) == []
        assert candidate_id in {r['id'] for r in expect(client.get(recipients,headers=owner))}
        items=expect(client.get(base+'/applications',headers=owner))
        assert items[0]['status']=='submitted' and items[0]['ats_report']['category']=='unsuitable'
        report_url='/api/v1/vacancies/applications/'+application['id']+'/ats/report'
        expect(client.get(report_url,headers=other),404)
        export=expect(client.get(report_url+'?download=true',headers=owner))
        assert '&lt;script&gt;' in export and '<script>bad</script>' not in export
        settings['mode']='manual';settings['min_experience_years']=1
        expect(client.put(base+'/ats/settings',headers=owner,json=settings))
        expect(client.post(base+'/ats/generate',headers=owner))
        expect(client.post(base+'/ats/recalculate',headers=owner))
        expect(client.patch('/api/v1/vacancies/applications/'+application['id'],headers=owner,json={'status':'accepted'}))
        items=expect(client.get(base+'/applications',headers=owner))
        assert items[0]['status']=='accepted' and items[0]['ats_report']['category']=='unsuitable'
        assert '/evaluate' in calls
        print('PASS: reports, employer isolation, configuration, generation preview, recalculate, escaped export, human decision overrides ATS recommendation')

if __name__=='__main__':
    asyncio.run(database_action(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True)
        subprocess.run([sys.executable,'-m','app.db.seed'],check=True)
        verify()
    finally: asyncio.run(database_action(False))

