"""Disposable DB: assigned algorithms run in the editor independently of daily catalog."""
import asyncio,base64,subprocess,sys,json
from uuid import uuid4
from fastapi.testclient import TestClient
from test_git_rewards import database

def verify():
    from app.main import app
    from app.api import practice
    from app.services.practice_service import tests
    values=dict(tests('reverse'));queued={}
    async def judge(path,method='GET',body=None):
        if method=='POST':key=str(len(queued));queued[key]=body;return {'token':key}
        body=queued[path.split('/')[2].split('?')[0]];inp=base64.b64decode(body['stdin']).decode()
        return {'status':{'id':3},'stdout':base64.b64encode(values[inp].encode()).decode(),'time':'.02','memory':3000}
    practice.judge=judge
    with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
        def ok(r,status=200):assert r.status_code==status,(r.status_code,r.text[:500]);return r.json()
        def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
        candidate=login('candidate@demo.local');employer=login('employer@demo.local')
        async def seed():
            from sqlalchemy import select
            from app.db.session import SessionLocal
            from app.models.user import User
            from app.models.candidate import CandidateProfile
            from app.models.employer import EmployerProfile
            from app.models.platform import EmployerTask,TaskAssignment
            from app.api.endpoint import save
            async with SessionLocal() as db:
                ep=await db.scalar(select(EmployerProfile).join(User,User.id==EmployerProfile.user_id).where(User.email=='employer@demo.local'))
                c=await db.scalar(select(CandidateProfile).join(User,User.id==CandidateProfile.user_id).where(User.email=='candidate@demo.local'))
                t=EmployerTask(employer_id=ep.id,title='Reverse',statement='Reverse input',language='python',rubric=[])
                db.add(t);await db.flush();a=TaskAssignment(task_id=t.id,candidate_id=c.id);db.add(a);await db.flush()
                await save(db,ep.user_id,'taskset:'+str(uuid4()),{'tasks':[{'id':1,'task_id':str(t.id),'practice_id':'custom:fixture','purpose':'practice','tests_json':json.dumps([{'input':i,'output':o} for i,o in tests('reverse')])}]});await db.commit();return str(a.id)
        aid=client.portal.call(seed);url='/api/practice/assignment/'+aid+'/check';code='print(" ".join(input().split()[::-1]))'
        ok(client.post(url,headers=employer,json={'source_code':code,'language_id':71}),403)
        ok(client.post('/api/practice/assignment/'+str(uuid4())+'/check',headers=candidate,json={'source_code':code,'language_id':71}),404)
        result=ok(client.post(url,headers=candidate,json={'source_code':code,'language_id':71}));assert result['solved'] and 'reward' not in result
        async def edit_after_start():
            from sqlalchemy import select
            from app.db.session import SessionLocal
            from app.models.platform import EmployerTask,TaskAssignment
            from app.models.endpoint import EndpointState
            async with SessionLocal() as db:
                from uuid import UUID
                assignment=await db.get(TaskAssignment,UUID(aid));task=await db.get(EmployerTask,assignment.task_id)
                task.language='java';task.statement='Changed after assignment'
                rows=(await db.execute(select(EndpointState).where(EndpointState.key.like('taskset:%')))).scalars().all()
                for row in rows:
                    if any(t.get('task_id')==str(task.id) for t in row.data.get('tasks',[])):
                        row.data={'tasks':[{'id':1,'task_id':str(task.id),'practice_id':'custom:fixture','purpose':'practice','time':'1','tests_json':'[{"input":"CHANGED","output":"WRONG"}]'}]}
                await db.commit()
        client.portal.call(edit_after_start)
        restored=next(t for t in ok(client.get('/api/v1/candidates/me/tasks',headers=candidate)) if t['id']==aid)
        assert restored['statement']=='Reverse input' and restored['check']['source_code']==code
        result=ok(client.post(url,headers=candidate,json={'source_code':code,'language_id':71}));assert result['solved']
        assert ok(client.get('/api/rewards',headers=candidate))['xp']==0
        submit='/api/v1/candidates/me/tasks/'+aid+'/submit'
        ok(client.post(submit,headers=candidate,json={'repo_url':'https://github.com/o/r'}),422)
        ok(client.post(submit,headers=candidate,json={'answer':code+'# changed'}),422)
        assert ok(client.post(submit,headers=candidate,json={'answer':code}))['auto_score']==1
        ok(client.post(url,headers=candidate,json={'source_code':code,'language_id':71}),409)
        print('PASS assignment ownership/editor check, GitHub rejected for algorithms, checked-code submission, no practice XP')

if __name__=='__main__':
    asyncio.run(database(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True);subprocess.run([sys.executable,'-m','app.db.seed'],check=True);verify()
    finally:asyncio.run(database(False))
