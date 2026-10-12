"""Server-managed generation credits. No mock payments or client-side grants."""
from fastapi import HTTPException
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from app.models.endpoint import EndpointState
import os

KEY='billing:generation'
PAID={'hiring','qualification'}
UNIT_RUB=2.5
COST=10
def demo_enabled():return os.getenv('BILLING_DEMO_ENABLED','false').lower()=='true'

async def balance(db,user_id):
    row=await db.get(EndpointState,(user_id,KEY))
    return int((row.data or {}).get('balance_units',0)) if row else 0

async def lock_balance(db,user_id):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'generation-billing:'+str(user_id)})
    await db.execute(insert(EndpointState).values(user_id=user_id,key=KEY,data={'balance_units':0}).on_conflict_do_nothing())
    return await db.scalar(select(EndpointState).where(EndpointState.user_id==user_id,EndpointState.key==KEY).with_for_update().execution_options(populate_existing=True))

async def require_credit(db,user_id,purpose):
    if purpose not in PAID:return None
    row=await lock_balance(db,user_id)
    if int(row.data.get('balance_units',0))<COST:
        raise HTTPException(402,'Генерация для отбора кандидатов и проверки квалификации доступна по платному тарифу. Алгоритмы и ручное создание бесплатны.')
    return row

def consume(row,purpose):
    if row is None:return
    data=dict(row.data);data['balance_units']=int(data['balance_units'])-COST
    data['used']=int(data.get('used',0))+1;data['last_purpose']=purpose;row.data=data

async def status(db,user_id):
    units=await balance(db,user_id)
    return {'balance_units':units,'credits':units//COST,'paid_purposes':sorted(PAID),'free_purposes':['practice'],
        'cost_per_generation':COST,'unit_price_rub':UNIT_RUB,'generation_price_rub':COST*UNIT_RUB,
        'demo':demo_enabled(),'checkout_available':demo_enabled(),'pricing_configured':True,
        'packages':[{'units':n,'generations':n//COST,'price_rub':n*UNIT_RUB} for n in (40,100,200)]}

async def demo_topup(db,user_id,units,request_id):
    if not demo_enabled():raise HTTPException(403,'Демонстрационное пополнение отключено')
    row=await lock_balance(db,user_id)
    key='billing:demo-topup:'+str(request_id)
    previous=await db.get(EndpointState,(user_id,key))
    if previous:
        if previous.data['units']!=units:raise HTTPException(409,'Номер пополнения уже использован с другой суммой')
        return await status(db,user_id)
    data=dict(row.data)
    if int(data.get('balance_units',0))+units>10000:raise HTTPException(422,'Лимит демонстрационного баланса — 10000 единиц')
    data['balance_units']=int(data.get('balance_units',0))+units
    data['demo']=True;row.data=data
    db.add(EndpointState(user_id=user_id,key=key,data={'units':units,'rub':units*UNIT_RUB,'demo':True}))
    await db.commit()
    return await status(db,user_id)
