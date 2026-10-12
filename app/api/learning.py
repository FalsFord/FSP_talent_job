import random
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.api.endpoint import state, save, candidate_only
from app.core.deps import get_db
from app.models.tasks import TaskItem
from app.tasks.grading import grade_answer

router=APIRouter(prefix='/api/learning',tags=['Learning'])

class Start(BaseModel):
    language:str=Field(pattern='^(python|java|sql)$')

class Answers(BaseModel):
    answers:dict[str,str|list[str]]=Field(default_factory=dict,max_length=5)

@router.post('/start')
async def start(body:Start,user=Depends(candidate_only),db=Depends(get_db)):
    previous=await state(db,user.id,'learning:active')
    if previous and not previous.get('done'): return previous
    rows=list((await db.execute(select(TaskItem).where(TaskItem.language==body.language,TaskItem.status=='active',
        TaskItem.kind.in_(['quiz_single','quiz_multi'])))).scalars().all())
    chosen=random.SystemRandom().sample(rows,min(5,len(rows)))
    if not chosen: raise HTTPException(409,'Вопросы для этого языка пока не добавлены')
    questions=[]
    for row in chosen:
        options=list(row.options);random.SystemRandom().shuffle(options)
        questions.append({'id':str(row.id),'statement':row.statement,'options':options,'kind':row.kind})
    data={'id':str(uuid4()),'questions':questions,'answers':{},'language':body.language}
    await save(db,user.id,'learning:active',data);await db.commit();return data

async def own(db,user,key):
    data=await state(db,user.id,'learning:active')
    if data.get('id')!=str(key) or data.get('done'): raise HTTPException(404,'Попытка не найдена или завершена')
    return data

@router.put('/{session_id}/answers')
async def answers(session_id:UUID,body:Answers,user=Depends(candidate_only),db=Depends(get_db)):
    data=await own(db,user,session_id)
    valid={q['id'] for q in data['questions']}
    if not set(body.answers)<=valid: raise HTTPException(422,'Неизвестный вопрос')
    if any(len(str(value))>8000 for value in body.answers.values()): raise HTTPException(422,'Ответ слишком длинный')
    data['answers']=body.answers
    await save(db,user.id,'learning:active',data);await db.commit();return {'saved':True}

@router.post('/{session_id}/submit')
async def submit(session_id:UUID,body:Answers,user=Depends(candidate_only),db=Depends(get_db)):
    data=await own(db,user,session_id);items=[]
    for question in data['questions']:
        row=await db.get(TaskItem,UUID(question['id']))
        result=grade_answer(row.kind,row.language,{}, {'correct':row.correct},body.answers.get(question['id']))
        items.append({'statement':row.statement,'passed':result.score==1,'explanation':row.explanation})
    result={'correct':sum(i['passed'] for i in items),'total':len(items),'items':items}
    if result['total']==5 and result['correct']>=4:
        from app.services.reward_service import award
        source=','.join(sorted(q['id'] for q in data['questions']))
        result['reward']=await award(db,user.id,'test','quiz:'+source)
    data.update(done=True,result=result)
    await save(db,user.id,'learning:active',data);await db.commit();return result
