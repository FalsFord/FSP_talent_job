import asyncio
import base64
from fastapi import APIRouter, Depends, HTTPException
from app.api.endpoint import judge, Submission, state, save, candidate_only
from app.core.deps import get_db
from app.services import daily_algorithms as daily
from app.services.reward_service import today
from sqlalchemy import text
from uuid import UUID

router = APIRouter(prefix='/api/practice', tags=['Practice'])

@router.get('')
async def catalog(user=Depends(candidate_only), db=Depends(get_db)):
    day=today().isoformat()
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key':'practice-catalog:'+str(user.id)})
    tasks=await state(db,user.id,'practice:daily:'+day,[])
    previous_tasks=tasks
    generation_notice=None
    progress = await state(db, user.id, 'practice:progress')
    # Preserve started attempts; untouched old template sets may use the new generator.
    if tasks and all(t.get('kind')!='gigachat' for t in tasks) and not any(progress.get(t['id']) for t in tasks):
        tasks=[]
    if not tasks:
        from app.tasks.rag.gigachat import GigaChatError
        try: tasks=await daily.generate(db,day,user_id=user.id)
        except ValueError as exc: raise HTTPException(503,str(exc))
        except GigaChatError as exc:
            if not previous_tasks: raise
            tasks=previous_tasks
            generation_notice='Новый набор пока недоступен: '+str(exc)+'. Сохранённый набор остаётся доступен.'
        if not generation_notice:
            await save(db,user.id,'practice:daily:'+day,tasks)
            await db.commit()
    public=('id','day','title','topic','level','statement','example','hint','sources','generation_method')
    return [{**{k:v for k,v in t.items() if k in public}, 'progress':progress.get(t['id']),
             **({'generation_notice':generation_notice} if generation_notice else {})} for t in tasks]

@router.post('/{task_id}/check')
async def check(task_id:str, body:Submission, user=Depends(candidate_only), db=Depends(get_db)):
    day=today().isoformat()
    tasks=await state(db,user.id,'practice:daily:'+day,[])
    task=next((t for t in tasks if t['id']==task_id),None)
    if not task: raise HTTPException(404,'Задание не найдено в сегодняшнем наборе. Обновите страницу.')
    return await run_checks(task_id,body,user,db,task)

@router.post('/company/{offer_id}/{task_id}/check')
async def company_check(offer_id:UUID,task_id:str,body:Submission,user=Depends(candidate_only),db=Depends(get_db)):
    from app.api.endpoint import invitations,InvitationStatus,EmployerProfile,invitation_tasks,expire_company_assessment
    inv,_=await invitations._load(db,user,offer_id)
    if inv.status!=InvitationStatus.accepted:raise HTTPException(403,'Сначала примите приглашение')
    progress=await expire_company_assessment(db,inv,user.id)
    if progress.get('done'):raise HTTPException(409,'Тестовое завершено или время истекло')
    if not progress:raise HTTPException(409,'Сначала начните выполнение тестового')
    ep=await db.get(EmployerProfile,inv.employer_id)
    taskset=await invitation_tasks(db,inv,ep.user_id)
    task=next((t for t in taskset if str(t['id'])==task_id),None)
    if not task or not task.get('practice_id'):raise HTTPException(404,'Алгоритм не найден')
    return await run_checks(task['practice_id'],body,user,db,task,company=True,storage_key='practice:offer:'+str(inv.id)+':'+str(task_id))

@router.post('/assignment/{assignment_id}/check')
async def assignment_check(assignment_id:UUID,body:Submission,user=Depends(candidate_only),db=Depends(get_db)):
    from app.api.endpoint import candidate_profile,TaskAssignment,EmployerTask
    from app.api.v1.tasks import assignment_clock
    from app.services.task_attempts import assignment_version
    p=await candidate_profile(db,user.id);a=await db.get(TaskAssignment,assignment_id)
    if not a or a.candidate_id!=p.id:raise HTTPException(404,'Задание не найдено')
    if a.status!='assigned':raise HTTPException(409,'Решение уже отправлено')
    task=await assignment_version(db,a,await db.get(EmployerTask,a.task_id))
    await assignment_clock(db,user.id,a,task)
    if not task.get('practice_id'):raise HTTPException(422,'Это не алгоритмическое задание')
    return await run_checks(task['practice_id'],body,user,db,task,company=True,storage_key='practice:assignment:'+str(a.id))

async def run_checks(task_id,body,user,db,task,company=False,storage_key=None):
    if body.language_id not in (63,71,54,62): raise HTTPException(422,'Неподдерживаемый язык')
    # Bound simultaneous submissions per account, including across API replicas.
    from app.chat_hub import chat_hub
    lock = chat_hub.redis.lock('practice:'+str(user.id), timeout=300, blocking_timeout=0)
    if not await lock.acquire(): raise HTTPException(429,'Дождитесь завершения текущей проверки')
    try:
        results=[]
        if company:
            from app.services.practice_service import tests,get_task
            if task_id.startswith('custom:'):
                import json
                try:
                    values=json.loads(task.get('tests_json','[]'))
                    if not isinstance(values,list) or not 1<=len(values)<=20:raise ValueError()
                    if any(not isinstance(v,dict) or not isinstance(v.get('input'),str) or not isinstance(v.get('output'),str) or len(v['input'])>20000 or len(v['output'])>20000 for v in values):raise ValueError()
                except (ValueError,TypeError):raise HTTPException(422,'Работодатель должен добавить от 1 до 20 тестов: input и output')
                test_cases=[(v['input'],v['output'],v.get('size',len(v['input'].split()))) for v in values]
            else:
                if not get_task(task_id):raise HTTPException(404,'Шаблон алгоритма не найден')
                test_cases=[(i,o,len(i.split()) if task_id!='brackets' else len(i)) for i,o in tests(task_id)]
        else:test_cases=daily.cases(task)
        for stdin, expected, n in test_cases:
            created=await judge('/submissions?base64_encoded=true&wait=false','POST',{
                'source_code':base64.b64encode(body.source_code.encode()).decode(),
                'stdin':base64.b64encode(stdin.encode()).decode(), 'language_id':body.language_id,
                'cpu_time_limit':2,'wall_time_limit':5,'memory_limit':128000,'enable_network':False})
            for _ in range(60):
                data=await judge('/submissions/'+created['token']+'?base64_encoded=true')
                if data['status']['id']>2: break
                await asyncio.sleep(.3)
            else: raise HTTPException(504,'Проверка заняла слишком много времени')
            for field in ('stdout','stderr','compile_output','message'):
                if data.get(field): data[field]=base64.b64decode(data[field]).decode('utf-8',errors='replace')
            passed=data['status']['id']==3 and (data.get('stdout') or '').strip()==expected.strip()
            results.append({'passed':passed,'n':n,'time':data.get('time'),'memory':data.get('memory'),
                'error':data.get('compile_output') or data.get('stderr') or data.get('message'), 'status':data['status']['id']})
            if data['status']['id']!=3: break
        total=len(test_cases); passed=sum(r['passed'] for r in results)
        output={'passed':passed,'total':total,'tests':results,'solved':passed==total,
            'status':{'id':3 if passed==total else results[-1]['status'] if results[-1]['status']!=3 else 4,
                      'description':'Все тесты пройдены' if passed==total else 'Есть ошибки'},
            'time':max(float(r['time'] or 0) for r in results),
            'memory':max(r['memory'] or 0 for r in results),
            'stderr':next((r['error'] for r in results if r['error']),None),
            'stdout':f'Пройдено тестов: {passed} из {total}'}
        progress=dict(await state(db,user.id,'practice:progress'))
        previous=progress.get(task_id,{})
        syntax_errors=previous.get('syntax_errors',0)+(1 if daily.syntax_failure(results) else 0)
        report=daily.assessment(results,passed,total,syntax_errors)
        output['assessment']=report
        output['daily_assessment']=previous.get('daily_assessment') or (report if output['solved'] else None)
        progress[task_id]={'solved':output['solved'] or progress.get(task_id,{}).get('solved',False),
                           'passed':passed,'total':total,'time':output['time'], 'attempts':previous.get('attempts',0)+1,
                           'syntax_errors':syntax_errors, 'daily_assessment':output['daily_assessment']}
        await save(db,user.id,'practice:progress',progress)
        await save(db,user.id,storage_key or 'practice:last:'+task_id,{'source_code':body.source_code,'language_id':body.language_id,'result':output})
        if output['solved'] and not company:
            from app.services.reward_service import award
            output['reward']=await award(db,user.id,'algorithm',task_id)
        await db.commit()
        return output
    finally:
        await lock.release()

