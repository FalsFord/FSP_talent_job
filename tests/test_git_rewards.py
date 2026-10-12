"""Integration contracts in a disposable database; no live candidate writes."""
import asyncio, os, subprocess, sys, time, json, hmac, hashlib
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
import asyncpg
from fastapi.testclient import TestClient

original=os.environ['DATABASE_URL']; name='git_rewards_'+uuid4().hex[:12]
os.environ['DATABASE_URL']=original.rsplit('/',1)[0]+'/'+name
os.environ['BACKGROUND_JOBS_ENABLED']='false'
os.environ['GIT_EVAL_WEBHOOK_SECRET']='integration-test-secret'

async def database(create):
    conn=await asyncpg.connect(original.replace('postgresql+asyncpg:','postgresql:'))
    try:await conn.execute(f'CREATE DATABASE "{name}"' if create else f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:await conn.close()

def verify():
    from app.main import app
    from app.services import git_eval_client
    calls=[]
    async def queue(**kwargs):calls.append(kwargs);return 'queued',None
    git_eval_client.submit_evaluation=queue
    with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
        def ok(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:500])
            return r.json() if r.content else None
        def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
        candidate=login('candidate@demo.local'); employer=login('employer@demo.local')
        async def seed():
            from sqlalchemy import select
            from app.db.session import SessionLocal
            from app.models.candidate import CandidateProfile
            from app.models.employer import EmployerProfile
            from app.models.platform import EmployerTask,TaskAssignment
            from app.models.user import User
            async with SessionLocal() as db:
                uid=await db.scalar(select(User.id).where(User.email=='candidate@demo.local'))
                c=await db.scalar(select(CandidateProfile).where(CandidateProfile.user_id==uid))
                ep=await db.scalar(select(EmployerProfile).join(User,User.id==EmployerProfile.user_id).where(User.email=='employer@demo.local'))
                t=EmployerTask(employer_id=ep.id,title='Git project',statement='Implement a project and tests',language='python',rubric=[])
                db.add(t);await db.flush();a=TaskAssignment(task_id=t.id,candidate_id=c.id)
                db.add(a);await db.commit();return str(a.id),str(t.id),uid
        aid,tid,uid=client.portal.call(seed)
        base='/api/v1/candidates/me/tasks/'+aid+'/submit'
        ok(client.post(base,headers=employer,json={'repo_url':'https://github.com/o/r'}),403)
        ok(client.post(base,headers=candidate,json={'repo_url':'https://127.0.0.1/o/r'}),422)
        ok(client.post(base,headers=candidate,json={'repo_url':'https://github.com/o/r','answer':'x'*30}),422)
        assert ok(client.post(base,headers=candidate,json={'repo_url':'https://github.com/o/r','ref':'main'}))['status']=='evaluating'
        assert calls[0]['ref']=='main'
        ok(client.post(base,headers=candidate,json={'answer':'x'*30}),409)
        ok(client.patch('/api/v1/employers/tasks/assignments/'+aid,headers=employer,json={'score':.8}),409)
        body=json.dumps({'external_id':aid,'status':'done','result':{'score':.8,'summary':['OK'],'breakdown':{}}}).encode()
        ts=str(int(time.time())); sig='sha256='+hmac.new(b'integration-test-secret',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        endpoint='/api/v1/internal/git-eval/callback'
        ok(client.post(endpoint,content=body),401)
        headers={'X-GitEval-Timestamp':ts,'X-GitEval-Signature':sig}
        ok(client.post(endpoint,content=body,headers=headers),204)
        ok(client.post(endpoint,content=body,headers=headers),204)
        rows=ok(client.get('/api/v1/employers/tasks/'+tid+'/assignments',headers=employer))
        assert rows[0]['auto_score']==.8 and rows[0]['eval_details']['summary']==['OK']
        ok(client.patch('/api/v1/employers/tasks/assignments/'+aid,headers=employer,json={'score':.8}))
        ok(client.patch('/api/v1/employers/tasks/assignments/'+aid,headers=employer,json={'score':.9}))
        assert ok(client.get('/api/rewards',headers=candidate))['xp']==10
        async def check_rewards():
            from app.db.session import SessionLocal
            from app.services.reward_service import award,progress,today
            now=datetime(2026,10,11,20,59,tzinfo=timezone.utc)
            assert today(now).isoformat()=='2026-10-11'
            assert today(now+timedelta(minutes=1)).isoformat()=='2026-10-12'
            # Separate account so simulated date does not collide with today's review reward.
            from app.models.endpoint import EndpointState
            async with SessionLocal() as db:
                await db.delete(await db.get(EndpointState,(uid,'learning:rewards')));await db.commit()
                assert (await award(db,uid,'algorithm','a',now))['earned']==10
                assert (await award(db,uid,'algorithm','a',now))['earned']==0
                assert (await award(db,uid,'algorithm','b',now))['earned']==0
                assert (await award(db,uid,'test','quiz',now))['earned']==10
                assert (await award(db,uid,'company','task',now))['earned']==10
                await db.commit()
                assert (await award(db,uid,'algorithm','b',now+timedelta(days=1)))['earned']==0
                assert (await award(db,uid,'algorithm','c',now+timedelta(days=1)))['earned']==10
                await db.commit()
                row=await db.get(EndpointState,(uid,'learning:rewards'))
                assert row.data['xp']==40 and row.data['streak']==2
                assert (await award(db,uid,'test','new',now+timedelta(days=3)))['earned']==10
                await db.commit();await db.refresh(row)
                assert row.data['streak']==1 and row.data['best_streak']==2
        client.portal.call(check_rewards)
        print('PASS: Git submission, ownership, review gating, signed callback/replay, employer override, reward deduplication, daily cap, Moscow midnight, streak/reset')

if __name__=='__main__':
    asyncio.run(database(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True)
        subprocess.run([sys.executable,'-m','app.db.seed'],check=True)
        verify()
    finally:asyncio.run(database(False))
