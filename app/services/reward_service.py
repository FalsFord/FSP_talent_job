"""Server-only rewards: one successful new activity per category/day, Moscow calendar."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from app.models.endpoint import EndpointState

KEY = 'learning:rewards'
CATEGORIES = {'algorithm', 'test', 'company'}

def today(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=3))).date()

async def award(db, user_id, category, source, now=None):
    if category not in CATEGORIES:
        raise ValueError('Unknown reward category')
    # All API replicas serialize the same account; caller commits the reward and result together.
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'rewards:'+str(user_id)})
    await db.execute(insert(EndpointState).values(user_id=user_id,key=KEY,data={}).on_conflict_do_nothing())
    row=await db.scalar(select(EndpointState).where(EndpointState.user_id==user_id,EndpointState.key==KEY).with_for_update().execution_options(populate_existing=True))
    data=dict(row.data or {})
    seen=dict(data.get('seen', {})); key=category+':'+str(source)
    if key in seen:
        return {'earned':0,'reason':'already_completed'}
    day=today(now).isoformat()
    seen[key]=day
    daily=dict(data.get('daily', {})) if data.get('day')==day else {}
    earned=0 if category in daily else 10
    if earned:
        previous=data.get('last_active')
        yesterday=(today(now)-timedelta(days=1)).isoformat()
        if previous!=day:
            data['streak']=data.get('streak',0)+1 if previous==yesterday else 1
        data['last_active']=day
        data['best_streak']=max(data.get('best_streak',0),data['streak'])
        daily[category]=10
        data['xp']=data.get('xp',0)+10
    data.update(seen=seen,day=day,daily=daily)
    row.data=data
    await db.flush()
    return {'earned':earned,'reason':'daily_limit' if not earned else 'success'}

async def progress(db,user_id):
    row=await db.get(EndpointState,(user_id,KEY))
    data=row.data if row else {}
    day=today(); active=data.get('last_active')
    streak=data.get('streak',0) if active in (day.isoformat(),(day-timedelta(days=1)).isoformat()) else 0
    daily=data.get('daily',{}) if data.get('day')==day.isoformat() else {}
    return {'xp':data.get('xp',0),'level':1+data.get('xp',0)//100,'streak':streak,'best_streak':data.get('best_streak',0),
            'daily':daily,'daily_limit':30,'earned_today':sum(daily.values()),'timezone':'Europe/Moscow'}
