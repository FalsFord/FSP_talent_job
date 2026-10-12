"""Disposable DB: mock topups, idempotency, paid generation, rollback and free algorithms."""
import asyncio,subprocess,sys,os
from uuid import uuid4
from types import SimpleNamespace
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_git_rewards import database
os.environ['BILLING_DEMO_ENABLED']='true'

def verify():
    from app.main import app
    from app.services import employer_task_service,knowledge_service
    calls=[]
    async def draft(*args,**kwargs):
        calls.append(kwargs)
        if kwargs.get('context_text','').endswith('fail'):raise HTTPException(503,'Model unavailable')
        return {'title':'Generated case','statement':'Explain algorithm and tradeoffs','rubric':[{'point':'Correctness','keywords':['test']}],'sources':['Test'],'source_details':[],'generation_method':'test','template_source':'Test'}
    async def retrieve(*args,**kwargs):return SimpleNamespace(text='array reverse',sources=['Test'],chunks=[])
    employer_task_service.draft_from_context=draft;knowledge_service.retrieve_context=retrieve
    with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
        def ok(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:500]);return r.json()
        def login(email):return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
        employer=login('employer@demo.local');candidate=login('candidate@demo.local')
        ok(client.post('/api/vacancies',headers=employer))
        endpoint='/api/me/generation-access';generate='/api/me/tasks/generate'
        access=lambda:ok(client.get(endpoint,headers=employer))
        assert access()['balance_units']==0 and access()['generation_price_rub']==25
        assert access()['unit_price_rub']==2.5 and access()['packages'][0]['price_rub']==100
        ok(client.post(generate,headers=employer,json={'purpose':'hiring'}),402);assert not calls
        request_id=str(uuid4());body={'units':40,'request_id':request_id}
        assert ok(client.post(endpoint+'/demo-topup',headers=employer,json=body))['balance_units']==40
        assert ok(client.post(endpoint+'/demo-topup',headers=employer,json=body))['balance_units']==40
        ok(client.post(endpoint+'/demo-topup',headers=employer,json={**body,'units':50}),409)
        ok(client.post(endpoint+'/demo-topup',headers=candidate,json=body),403)
        ok(client.post(endpoint+'/demo-topup',headers=employer,json={'units':-5,'request_id':str(uuid4())}),422)
        os.environ['BILLING_DEMO_ENABLED']='false'
        ok(client.post(endpoint+'/demo-topup',headers=employer,json={'units':20,'request_id':str(uuid4())}),403)
        os.environ['BILLING_DEMO_ENABLED']='true'
        ok(client.post(generate,headers=employer,json={'purpose':'hiring','focus':'fail'}),503)
        assert access()['balance_units']==40
        tasks=ok(client.post(generate,headers=employer,json={'purpose':'hiring'}));assert access()['balance_units']==30
        ok(client.post(generate,headers=employer,json={'purpose':'qualification','replace_id':tasks[0]['id']}));assert access()['balance_units']==20
        ok(client.post(generate,headers=employer,json={'purpose':'practice','grade':'junior'}));assert access()['balance_units']==20
        ok(client.post(generate,headers=employer,json={'purpose':'qualification'}));assert access()['balance_units']==10
        ok(client.post(generate,headers=employer,json={'purpose':'hiring'}));assert access()['balance_units']==0
        before=len(calls);ok(client.post(generate,headers=employer,json={'purpose':'qualification'}),402);assert len(calls)==before
        workspace=ok(client.get('/api/workspace',headers=employer))
        assert len(workspace['tasks'])==4 and workspace['billing']['balance_units']==0
        print('PASS units/ruble pricing, replay-safe demo topup, roles, demo-off, paid generation/regeneration, failure rollback, free algorithms, insufficient balance')

if __name__=='__main__':
    asyncio.run(database(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True);subprocess.run([sys.executable,'-m','app.db.seed'],check=True);verify()
    finally:asyncio.run(database(False))

