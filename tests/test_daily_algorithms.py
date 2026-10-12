"""Disposable DB integration: RAG catalog, private oracles, attempts and immutable daily score."""
import asyncio
import base64
import subprocess
import sys
from types import SimpleNamespace
from fastapi.testclient import TestClient
from test_git_rewards import database

def verify():
    from app.main import app
    from app.services import daily_algorithms as daily
    from app.api import practice
    # This test isolates scoring of the deterministic fallback catalog. Model
    # generation, private tests and caching are covered by test_algorithm_generation.
    original_generate=daily.generate
    async def fallback_generate(db,day,**kwargs): return await original_generate(db,day)
    daily.generate=fallback_generate
    context=SimpleNamespace(chunks=[{'text':'array массив sum сумма unique множество stack стек prefix префикс sequence последовательность', 'label':'Test algorithms'}])
    async def retrieve(*args,**kwargs): return context
    daily.knowledge_service.retrieve_context=retrieve
    submissions={}; checks=[]
    async def judge(path, method='GET', body=None):
        if method=='POST':
            token=str(len(submissions)); submissions[token]=body; return {'token':token}
        body=submissions[path.split('/')[2].split('?')[0]]
        code=base64.b64decode(body['source_code']).decode()
        stdin=base64.b64decode(body['stdin']).decode()
        if code=='syntax': return {'status':{'id':6},'compile_output':base64.b64encode(b'SyntaxError: invalid syntax').decode()}
        expected=next(out for inp,out,n in checks if inp==stdin)
        return {'status':{'id':3},'stdout':base64.b64encode(expected.encode()).decode(),'time':'.08','memory':16000}
    practice.judge=judge
    with TestClient(app,headers={'Origin':'http://127.0.0.1:3001'}) as client:
        def ok(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:500])
            return r.json()
        def login(email): return {'Authorization':'Bearer '+ok(client.post('/api/auth/login',json={'email':email,'password':'demo1234'}))['access_token']}
        candidate=login('candidate@demo.local'); employer=login('employer@demo.local')
        tasks=ok(client.get('/api/practice',headers=candidate)); assert len(tasks)==4
        assert all('seed' not in t and 'kind' not in t and t['sources']==['Test algorithms'] for t in tasks)
        assert tasks==ok(client.get('/api/practice',headers=candidate))
        ok(client.get('/api/practice',headers=employer),403)
        generated=client.portal.call(daily.generate,None,daily.today().isoformat())
        checks[:]=daily.cases(generated[0]); task_id=tasks[0]['id']
        route='/api/practice/'+task_id+'/check'
        bad=ok(client.post(route,headers=candidate,json={'source_code':'syntax','language_id':71}))
        assert bad['assessment']['syntax_errors']==1 and bad['daily_assessment'] is None
        good=ok(client.post(route,headers=candidate,json={'source_code':'correct','language_id':71}))
        assert good['solved'] and good['daily_assessment']['components']['syntax']==8 and good['reward']['earned']==10
        again=ok(client.post(route,headers=candidate,json={'source_code':'syntax','language_id':71}))
        assert again['daily_assessment']==good['daily_assessment']
        last=ok(client.get('/api/practice',headers=candidate))[0]['progress']
        assert last['solved'] and last['attempts']==3 and last['daily_assessment']==good['daily_assessment']
        assert ok(client.get('/api/rewards',headers=candidate))['xp']==10
        ok(client.post('/api/practice/1900-01-01-sum/check',headers=candidate,json={'source_code':'x','language_id':71}),404)
        context.chunks=[]
        try:client.portal.call(daily.generate,None,'2100-01-01')
        except ValueError:pass
        else:raise AssertionError('Empty RAG silently fell back')
    linear=[{'n':n,'passed':True,'time':str(n/1000),'memory':10} for n in (250,2500,10000)]
    assert daily.complexity(linear)['estimate']=='O(n)'
    assert daily.complexity([{**r,'time':'.01'} for r in linear])['estimate'] is None
    assert not daily.syntax_failure([{'error':'NameError: missing_variable'}])
    for kind in daily.KINDS:
        cs=daily.cases({'kind':kind,'parameter':3,'seed':42})
        assert len(cs)>=7 and cs[-1][2]==10000
    print('PASS RAG daily catalog, private tests, syntax history, score freeze, XP deduplication, stale tasks, complexity/noise')

if __name__=='__main__':
    asyncio.run(database(True))
    try:
        subprocess.run([sys.executable,'-m','app.db.init_db'],check=True)
        subprocess.run([sys.executable,'-m','app.db.seed'],check=True)
        verify()
    finally: asyncio.run(database(False))
