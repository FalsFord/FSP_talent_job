"""Exercise real Reqcore + local Ollama using synthetic candidates only."""
import json
import os
import time
import httpx

headers={'X-Service-Token':os.environ['ATS_SERVICE_TOKEN']}
vacancy=dict(title='Python backend developer',description='Middle разработчик. От 3 лет разработки Python API, PostgreSQL и тестирование. Удалённая работа.',grade='middle',experience='от 3 лет',skills=['Python','PostgreSQL'],work_format='remote',salary_max=180000)
with httpx.Client(timeout=330,headers=headers) as client:
    def call(path,body):
        r=client.post('http://ats:8011/'+path,json=body)
        r.raise_for_status()
        return r.json()
    for attempt in range(30):
        try:
            call('status',{})
            break
        except httpx.HTTPError:
            if attempt == 29:
                raise
            time.sleep(1)
    criteria=call('auto-config',vacancy)
    candidates={
        'suitable':dict(grade='middle',grade_verified=True,experience_min=5,experience_max=5,experience_evidence='5 лет backend-разработки',skills=['Python','PostgreSQL','FastAPI'],work_formats=['remote'],salary_min=150000,work_experience=[dict(company='Example',position='Backend developer',period='2021–2026',description='Разрабатывал API на Python и FastAPI, оптимизировал PostgreSQL, писал unit-тесты.')]),
        'unsuitable':dict(grade='junior',grade_verified=True,experience_min=0,experience_max=0,experience_evidence='Без опыта',skills=['HTML','CSS'],work_formats=['office'],salary_min=250000,work_experience=[]),
    }
    reports={}
    for expected,candidate in candidates.items():
        begin=time.monotonic()
        report=call('evaluate',dict(candidate=candidate,criteria=criteria,vacancy=vacancy,cover_letter='Интересует работа в команде'))
        assert report['provider']=='Reqcore' and report['criteria'],report
        if expected=='unsuitable': assert report['category']=='unsuitable',report
        if expected=='suitable': assert report['category']=='suitable' and report['score']>=75,report
        reports[expected]=report
        print(expected,report['category'],report['score'],report['coverage'],round(time.monotonic()-begin,1),'seconds',flush=True)
    generated=call('generate-config',vacancy)
    assert generated['source']=='reqcore_ai' and generated['reqcore_criteria'],generated
    call('validate-config',generated)
    reports['generated_criteria']=generated
    with open('/tmp/reqcore-live.json','w',encoding='utf-8') as f: json.dump(reports,f,ensure_ascii=False,indent=2)
    print('PASS: real local model, Reqcore scoring, explanatory reports, AI criteria generation.',flush=True)
