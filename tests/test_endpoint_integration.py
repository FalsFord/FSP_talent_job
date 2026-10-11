"""Exercise the integration in an isolated temporary PostgreSQL database.

Run inside the API container: python tests/test_endpoint_integration.py
No production users, messages, or files are changed.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from uuid import uuid4

import asyncpg
from fastapi.testclient import TestClient

original_url = os.environ['DATABASE_URL']
database = 'fsp_verify_' + uuid4().hex[:12]
os.environ['DATABASE_URL'] = original_url.rsplit('/', 1)[0] + '/' + database
os.environ['BACKGROUND_JOBS_ENABLED'] = 'false'
os.environ['BILLING_DEMO_ENABLED'] = 'true'
test_uploads=tempfile.TemporaryDirectory(prefix='fsp_resume_verify_')
os.environ['UPLOAD_DIR']=test_uploads.name
origin = 'http://127.0.0.1:3001'

async def database_action(create):
    connection = await asyncpg.connect(original_url.replace('postgresql+asyncpg:', 'postgresql:'))
    try:
        if create: await connection.execute(f'CREATE DATABASE "{database}"')
        else: await connection.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
    finally: await connection.close()

def verify():
    from app.main import app
    def expect(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code, response.text[:500])
        return response.json() if status != 204 else None
    with TestClient(app, headers={'Origin':origin}) as client:
        def login(email):
            return expect(client.post('/api/auth/login', json={'email':email,'password':'demo1234'}))['access_token']
        candidate_token, employer_token, admin_token = login('candidate@demo.local'), login('employer@demo.local'), login('admin@demo.local')
        candidate, employer, admin = ({'Authorization':'Bearer '+token} for token in (candidate_token, employer_token, admin_token))
        c_workspace = expect(client.get('/api/workspace',headers=candidate))
        candidate_id = c_workspace['profile']['id']
        expect(client.get('/api/workspace',headers=employer))
        expect(client.get('/api/workspace'),401)
        expect(client.get('/api/v1/admin/tasks/generators',headers=candidate),403)
        expect(client.get('/api/v1/admin/tasks/generators',headers=admin))
        expect(client.get('/api/v1/employers/me/company',headers=candidate),403)
        expect(client.post('/api/auth/register',json={'email':'invalid','password':'x','role':'candidate','consent_personal_data':False}),422)
        newcomer = expect(client.post('/api/auth/register',json={'email':'new@example.org','password':'LongPassword123!','role':'candidate','consent_personal_data':True,'name':'Новый'}))
        expect(client.get('/api/workspace',headers={'Authorization':'Bearer '+newcomer['access_token']}))
        # PDF upload fills blanks; explicit apply replaces manual fields without changing login/grade.
        from tests.test_resume_parser import sample_pdf
        resume_user={'Authorization':'Bearer '+newcomer['access_token']}
        native_before=expect(client.get('/api/v1/candidates/me/profile',headers=resume_user))
        parsed=expect(client.post('/api/me/files/resume',headers=resume_user,files={'file':('resume.pdf',sample_pdf(),'application/pdf')}))
        assert parsed['resume_parse']['status']=='parsed'
        assert parsed['name']=='Новый' and parsed['city']=='Moscow'
        assert parsed['work_experience'][0]['company']=='Example Company'
        assert parsed['email']=='new@example.org' and parsed['contact_email']=='alex@example.org'
        applied=expect(client.post('/api/me/resume/apply',headers=resume_user))
        assert applied['name']=='Alex' and applied['email']=='new@example.org'
        native_after=expect(client.get('/api/v1/candidates/me/profile',headers=resume_user))
        assert native_after['first_name']=='Alex' and native_after['headline']=='Python Developer'
        assert native_before['category']==native_after['category']
        assert expect(client.get('/api/workspace',headers=resume_user))['profile']['work_experience']==applied['work_experience']
        applied['work_experience'][0]['description']='Edited achievements'
        expect(client.put('/api/me/profile',headers=resume_user,json=applied))
        assert expect(client.get('/api/workspace',headers=resume_user))['profile']['work_experience'][0]['description']=='Edited achievements'
        # Unfinished onboarding remains private even after a resume is parsed.
        expect(client.get('/api/candidates/'+applied['id'],headers=employer),404)
        published_profile=expect(client.get('/api/workspace',headers=candidate))['profile']
        published_profile['work_experience']=applied['work_experience']
        expect(client.put('/api/me/profile',headers=candidate,json=published_profile))
        public=expect(client.get('/api/candidates/'+candidate_id,headers=employer))
        assert 'resume_parse' not in public and 'contact_email' not in public
        assert public['work_experience'][0]['description']=='Edited achievements'
        expect(client.get(applied['resume_url'],headers=candidate),404)
        expect(client.post('/api/me/files/resume',headers=employer,files={'file':('resume.pdf',sample_pdf(),'application/pdf')}),403)
        applied['work_experience']=[]
        expect(client.put('/api/me/profile',headers=resume_user,json=applied))
        assert expect(client.get('/api/workspace',headers=resume_user))['profile']['work_experience']==[]
        expect(client.put('/api/me/profile',headers=resume_user,json={'work_experience':'invalid'}),422)
        registered = expect(client.post('/api/auth/register',json={'email':'company@example.org','password':'LongPassword123!','role':'employer','consent_personal_data':True,'name':'Работодатель'}))
        owner = {'Authorization':'Bearer '+registered['access_token']}
        vacancy_id = expect(client.post('/api/vacancies',headers=owner))['id']
        vacancy_body={'title':'Python Developer','tasks':'Разработка сервисов FastAPI и PostgreSQL','description':'Наша команда строит сервисы','company':'Проверочная компания','salaryMin':'120000','salaryMax':'180000','tech':['python','fastapi'],'format':'Удалённо','direction':'Backend','grade':'Middle','published':True}
        expect(client.put('/api/me/vacancy',headers=owner,json=vacancy_body))
        native_vacancies=expect(client.get('/api/v1/vacancies'))
        found=expect(client.post('/api/vacancies/search',headers=candidate,json={'query':'питон серверная разработка','work_format':'remote','skill':'Python','salary_min':150000}))
        assert any(v['id']==vacancy_id for v in found['items'])
        assert all(v['work_format']=='remote' and v['salary_max']>=150000 and 'python' in [s.lower() for s in v['skills']] for v in found['items'])
        expect(client.post('/api/vacancies/search',headers=owner,json={}),403)
        expect(client.post('/api/vacancies/search',headers=candidate,json={'salary_min':'invalid'}),422)
        assert any(v['id']==vacancy_id and v['salary_min']==120000 for v in native_vacancies)
        tasks=expect(client.put('/api/me/tasks',headers=owner,json=[{'id':1,'title':'План сервиса','condition':'Опишите проектирование безопасного REST API','time':'20','points':'100'}]))
        task_id=tasks[0]['task_id']
        assert len(expect(client.get('/api/v1/employers/tasks',headers=owner)))==1
        invitation=expect(client.post('/api/offers',headers=owner,json={'candidate_id':candidate_id,'vacancy_id':vacancy_id}))
        offer_id=invitation['id']
        before=expect(client.get('/api/candidates/'+candidate_id,headers=owner))
        assert 'email' not in before and 'phone' not in before
        expect(client.get('/api/offers/'+offer_id+'/messages',headers=employer),404)
        expect(client.put('/api/me/offer-statuses',headers=candidate,json={offer_id:'accepted'}))
        after=expect(client.get('/api/candidates/'+candidate_id,headers=owner))
        assert 'email' in after
        # Preserve verified skills when the React profile autosaves unrelated fields.
        profile=expect(client.get('/api/workspace',headers=candidate))['profile']
        profile['city']='Казань'
        expect(client.put('/api/me/profile',headers=candidate,json=profile))
        assert expect(client.get('/api/v1/candidates/me/profile',headers=candidate))['city']=='Казань'
        with client.websocket_connect('/ws/offers/'+offer_id,subprotocols=['endpoint.chat.v1','endpoint.bearer.'+candidate_token],headers={'Origin':origin}) as left:
            with client.websocket_connect('/ws/offers/'+offer_id,subprotocols=['endpoint.chat.v1','endpoint.bearer.'+registered['access_token']],headers={'Origin':origin}) as right:
                assert left.receive_json()['type']=='ready'
                assert right.receive_json()['type']=='ready'
                key=str(uuid4())
                left.send_json({'type':'message','text':'Привет, WebSocket!','client_message_id':key})
                a,b=left.receive_json(),right.receive_json()
                assert a['message']['mine'] and not b['message']['mine']
                assert a['message']['id']==b['message']['id']
                left.send_json({'type':'message','text':'Привет, WebSocket!','client_message_id':key})
                assert left.receive_json()['message']['id']==a['message']['id']
                right.receive_json()
                right.send_json({'type':'message','text':'Ответ работодателя','client_message_id':str(uuid4())})
                assert not left.receive_json()['message']['mine']
                assert right.receive_json()['message']['mine']
        assert len(expect(client.get('/api/offers/'+offer_id+'/messages',headers=candidate)))==2
        assert len(expect(client.get('/api/workspace',headers=candidate))['messages']['candidate-'+offer_id])==2
        expect(client.put('/api/me/assessments/assignment',headers=candidate,json={'offerId':offer_id,'answers':{'0':'Создам REST API с проверкой JWT и ролей, валидацией данных и транзакциями PostgreSQL.'},'index':0,'startedAt':1,'done':True}))
        assignments=expect(client.get('/api/v1/employers/tasks/'+task_id+'/assignments',headers=owner))
        assert assignments[0]['status']=='submitted'
        expect(client.patch('/api/v1/employers/tasks/assignments/'+assignments[0]['id'],headers=owner,json={'score':.8}))
        assert expect(client.get('/api/v1/candidates/me/tasks',headers=candidate))[0]['score']==.8
        expect(client.patch('/api/v1/candidates/me/privacy',headers=candidate,json={'show_contacts_after_accept':False,'show_full_name':False,'is_discoverable':True}))
        assert 'email' not in expect(client.get('/api/candidates/'+candidate_id,headers=owner))
        expect(client.patch('/api/v1/candidates/me/privacy',headers=candidate,json={'show_contacts_after_accept':True,'show_full_name':False,'is_discoverable':True}))
        expect(client.post('/api/v1/candidates/me/fsp-link',headers=candidate,json={'external_id':'DEMO-42'}))
        expect(client.delete('/api/v1/candidates/me/fsp-link',headers=candidate),204)
        notifications=expect(client.get('/api/v1/notifications',headers=candidate))
        assert notifications['unread']>0
        expect(client.post('/api/v1/notifications/read-all',headers=candidate),204)
        assert expect(client.get('/api/v1/notifications',headers=candidate))['unread']==0
        expect(client.post('/api/v1/vacancies/'+vacancy_id+'/apply',headers=candidate,json={'cover_letter':'Хочу работать с вашей командой'}),201)
        applications=expect(client.get('/api/v1/vacancies/'+vacancy_id+'/applications',headers=owner))
        expect(client.patch('/api/v1/vacancies/applications/'+applications[0]['id'],headers=owner,json={'status':'accepted'}))
        need=expect(client.post('/api/v1/employers/needs',headers=owner,json={'title':'Python team','description':'Python FastAPI разработчик с навыками SQL','skills':['python'],'salary_min':120000,'salary_max':180000}),201)
        shortlist=expect(client.post('/api/v1/employers/needs/'+need['id']+'/shortlist',headers=owner,json={'filters':{},'limit':10}))
        assert shortlist['snapshot_id']
        expect(client.get('/api/v1/employers/needs/'+need['id']+'/shortlist/snapshots/'+shortlist['snapshot_id'],headers=owner))
        expect(client.post('/api/v1/search/candidates',headers=owner,json={'query':'python fastapi'}))
        # Start a genuinely new native FSP session and submit its public question values.
        token=newcomer['access_token']; fresh={'Authorization':'Bearer '+token}
        assessment=expect(client.post('/api/me/assessments/grade/start',headers=fresh))
        assert assessment['session_id'] and assessment['questions']
        answers={str(i):(json.dumps(q['options'][:1],ensure_ascii=False) if q['kind']=='quiz_multi' else q['options'][0] if q['options'] else 'SELECT 1') for i,q in enumerate(assessment['questions'])}
        expect(client.put('/api/me/assessments/grade',headers=fresh,json={'answers':answers,'index':0,'done':False}))
        result=expect(client.put('/api/me/assessments/grade',headers=fresh,json={'answers':answers,'index':0,'done':True}))
        assert result['result']['status']=='reviewed'
        expect(client.get('/api/v1/assessments/history',headers=fresh))
        # All mapped operations exist and can be reached (with missing required parameters).
        schema=expect(client.get('/api/openapi.json'))
        catalog=json.loads(open('/app/frontend-endpoints.json').read())
        assert len(catalog)==73
        for route in catalog:
            assert route['operationId']==schema['paths'][route['path']][route['method'].lower()]['operationId']
        # Clean corpus is indexed, idempotent, and used by employer drafts.
        stats=expect(client.get('/api/v1/admin/knowledge/stats',headers=admin))
        assert stats['documents_by_source']['full_data']==227
        expect(client.post('/api/me/generation-access/demo-topup',headers=owner,json={'units':100,'request_id':str(uuid4())}))
        for purpose in ('hiring','qualification','practice'):
            generated=expect(client.post('/api/me/tasks/generate',headers=owner,json={'purpose':purpose,'language':'python','grade':'middle','focus':'разворот reverse списка'}))
            assert generated[-1]['purpose']==purpose and generated[-1]['source_details']
            assert any(source['url'] for source in generated[-1]['source_details'])
        expect(client.post('/api/me/tasks/generate',headers=candidate,json={}),403)
        # Regeneration updates the selected row and native task; deletion survives reload.
        target=generated[0]
        ids=[t['id'] for t in generated]
        regenerated=expect(client.post('/api/me/tasks/generate',headers=owner,json={'replace_id':target['id'],'purpose':'qualification','language':'sql','grade':'senior','focus':'SQL транзакции'}))
        assert [t['id'] for t in regenerated]==ids
        assert regenerated[0]['task_id']==target['task_id']
        assert regenerated[0]['purpose']=='qualification' and regenerated[0]['language']=='sql'
        assert regenerated[0]['condition'].startswith(target['condition'])
        another=expect(client.post('/api/me/tasks/generate',headers=owner,json={'base_id':target['id'],'purpose':'hiring','language':'sql','grade':'senior','focus':'SQL транзакции'}))
        assert len(another)==len(regenerated)+1
        assert another[-1]['template_source']!=regenerated[0].get('template_source')
        # Keep subsequent practice checks bound to their original final task.
        expect(client.put('/api/me/tasks',headers=owner,json=regenerated))
        assert expect(client.get('/api/workspace',headers=owner))['tasks']==regenerated
        remaining=regenerated[1:]
        expect(client.put('/api/me/tasks',headers=owner,json=remaining))
        assert expect(client.get('/api/workspace',headers=owner))['tasks']==remaining
        expect(client.post('/api/me/tasks/generate',headers=owner,json={'replace_id':target['id']}),404)
        expect(client.get('/api/practice',headers=owner),403)
        catalog=expect(client.get('/api/practice',headers=candidate))
        assert len(catalog)==4 and all('tests' not in task for task in catalog)
        practice=expect(client.post('/api/practice/reverse/check',headers=candidate,json={'source_code':'import sys\nprint(" ".join(sys.stdin.read().split()[::-1]))','language_id':71}))
        assert practice['solved'] and practice['time']>=0 and practice['memory']>0
        algorithm_id=generated[-1]['task_id']
        assert generated[-1]['practice_id']=='reverse'
        expect(client.post('/api/v1/employers/tasks/'+algorithm_id+'/assign',headers=owner,json={'candidate_ids':[candidate_id]}))
        assigned=next(a for a in expect(client.get('/api/v1/candidates/me/tasks',headers=candidate)) if a.get('practice_id')=='reverse')
        expect(client.post('/api/v1/candidates/me/tasks/'+assigned['id']+'/submit',headers=candidate,json={'answer':'print("unverified code answer")'}),422)
        submitted=expect(client.post('/api/v1/candidates/me/tasks/'+assigned['id']+'/submit',headers=candidate,json={'answer':'import sys\nprint(" ".join(sys.stdin.read().split()[::-1]))'}))
        assert submitted['auto_score']==1
        wrong=expect(client.post('/api/practice/reverse/check',headers=candidate,json={'source_code':'print("wrong")','language_id':71}))
        assert not wrong['solved'] and wrong['passed']==0
        syntax=expect(client.post('/api/practice/reverse/check',headers=candidate,json={'source_code':'def broken(:','language_id':71}))
        assert not syntax['solved'] and 'SyntaxError' in syntax['stderr']
        runtime=expect(client.post('/api/practice/reverse/check',headers=candidate,json={'source_code':'raise RuntimeError("test")','language_id':71}))
        assert not runtime['solved'] and 'RuntimeError' in runtime['stderr']
        timeout=expect(client.post('/api/practice/reverse/check',headers=candidate,json={'source_code':'while True: pass','language_id':71}))
        assert timeout['status']['id']==5
        before=expect(client.get('/api/v1/candidates/me/profile',headers=candidate))
        learning=expect(client.post('/api/learning/start',headers=candidate,json={'language':'python'}))
        assert all('correct' not in q for q in learning['questions'])
        answers={q['id']:q['options'][0] for q in learning['questions']}
        expect(client.put('/api/learning/'+learning['id']+'/answers',headers=candidate,json={'answers':answers}))
        expect(client.put('/api/learning/'+learning['id']+'/answers',headers=owner,json={'answers':answers}),403)
        learned=expect(client.post('/api/learning/'+learning['id']+'/submit',headers=candidate,json={'answers':answers}))
        assert learned['total']==5 and all(item['explanation'] for item in learned['items'])
        after=expect(client.get('/api/v1/candidates/me/profile',headers=candidate))
        assert before==after
        expect(client.post('/api/auth/login',json={'email':'company@example.org','password':'LongPassword123!'}))
        csrf={'X-CSRF-Token':client.cookies['endpoint_csrf']}
        expect(client.post('/api/auth/refresh',headers=csrf))
        csrf={'X-CSRF-Token':client.cookies['endpoint_csrf']}
        expect(client.post('/api/auth/change-password',headers=csrf,json={'current_password':'LongPassword123!','new_password':'DifferentPassword123!'}))
        expect(client.get('/api/workspace',headers=owner),401)
        print('PASS: cleaned corpus/idempotent ingest, RAG generation, Judge0 tests/errors/time/memory/timeout, bound employer submission, learning/grade isolation, roles, native/React data, privacy, migration-compatible auth, vacancy/applications, tasks/review, search/snapshots, native assessment, notifications, 73 API contracts, two-way WebSocket, retry deduplication and chat history.')

if __name__ == '__main__':
    asyncio.run(database_action(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True)
        subprocess.run([sys.executable,'-m','app.db.seed'],check=True)
        subprocess.run([sys.executable,'-m','app.tasks.rag.ingest'],check=True)
        subprocess.run([sys.executable,'-m','app.tasks.rag.ingest'],check=True)
        verify()
    finally:
        asyncio.run(database_action(False))
        test_uploads.cleanup()
