"""Adapter for the existing React screens. Business actions use FSP v1 handlers.

Additional state is only for fields absent upstream: files, editor drafts and UI settings.
"""
import asyncio
import base64
import json
import io
import zipfile
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.v1 import auth, candidates, employers, invitations, vacancies, assessments, tasks
from app.api.v1._common import candidate_profile, employer_profile
from app.core.errors import DomainError
from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_roles
from app.core.security import create_access_token, decode_token, hash_password, verify_password, password_version
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.models.candidate import CandidateProfile, CandidateSkill, Category
from app.models.reference import Grade, Specialization
from app.models.invitation import Invitation, InvitationStatus
from app.models.platform import EmployerTask, TaskAssignment
from app.models.vacancy import Vacancy,Application,ApplicationStatus
from app.models.employer import EmployerProfile
from app.models.endpoint import EndpointState, ChatMessage
from app.schemas.common import RegisterIn, LoginIn
from app.schemas.candidate import CandidateProfileUpdate
from app.schemas.employer import CompanyUpdate
from app.schemas.invitation import InvitationCreate
from app.schemas.assessment import OnboardingStartIn, AnswerIn, SubmitAnswersIn
from app.chat_hub import chat_hub

router = APIRouter(tags=['EndPoint integration'])
candidate_only = require_roles(UserRole.candidate)
employer_only = require_roles(UserRole.employer)
UPLOADS = Path(os.getenv('UPLOAD_DIR', '/app/uploads'))
UPLOADS.mkdir(parents=True, exist_ok=True)
FORMATS = {'remote': 'Удалённо', 'office': 'В офисе', 'hybrid': 'Гибрид'}

async def state(db, user_id, key, default=None):
    row = await db.get(EndpointState, (user_id, key))
    return row.data if row else (default if default is not None else {})

async def save(db, user_id, key, data):
    row = await db.get(EndpointState, (user_id, key))
    if row: row.data = data
    else: db.add(EndpointState(user_id=user_id, key=key, data=data))
    await db.flush()
    return data

def user_out(user):
    return {'id': str(user.id), 'email': user.email, 'role': user.role.value, 'name':user.email.split('@')[0]}

def set_cookie(response, token):
    response.set_cookie('endpoint_session', token, httponly=True, secure=os.getenv('COOKIE_SECURE') == 'true',
                        samesite='strict', path='/api', max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie('endpoint_csrf', secrets.token_urlsafe(24), secure=os.getenv('COOKIE_SECURE') == 'true',
                        samesite='strict', path='/', max_age=settings.access_token_expire_minutes * 60)

def check_origin(request):
    if request.headers.get('origin') not in settings.cors_origin_list:
        raise HTTPException(403, 'Недопустимый источник запроса.')

def check_csrf(request):
    check_origin(request)
    supplied = request.headers.get('x-csrf-token', '')
    if not supplied or not secrets.compare_digest(supplied, request.cookies.get('endpoint_csrf', '')):
        raise HTTPException(403, 'Обновите страницу и повторите запрос.')

@router.post('/api/auth/{action}')
async def authentication(action: str, request: Request, response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    check_origin(request)
    if action in ('refresh', 'logout', 'change-password'):
        check_csrf(request)
        token = request.cookies.get('endpoint_session')
        if not token: raise HTTPException(401, 'Войдите в аккаунт')
        user = await get_current_user(db, HTTPAuthorizationCredentials(scheme='Bearer', credentials=token))
        if action == 'logout':
            response.delete_cookie('endpoint_session', path='/api')
            response.delete_cookie('endpoint_csrf', path='/')
            return {'ok': True}
        if action == 'change-password':
            if not verify_password(body.get('current_password',''), user.password_hash):
                raise HTTPException(400, 'Неверный текущий пароль')
            password = body.get('new_password','')
            if not 10 <= len(password) <= 128: raise HTTPException(422, 'Пароль: 10–128 символов')
            user.password_hash = hash_password(password)
            await db.commit()
            response.delete_cookie('endpoint_session', path='/api')
            response.delete_cookie('endpoint_csrf', path='/')
            return {'ok': True}
        new_token = create_access_token(str(user.id), {'role': user.role.value, 'ver': password_version(user)})
        set_cookie(response, new_token)
        return {'access_token': new_token, 'user': user_out(user)}
    if action == 'register':
        result = await auth.register(RegisterIn.model_validate(body), db)
    elif action == 'login':
        result = await auth.login(LoginIn.model_validate(body), db)
    else: raise HTTPException(404, 'Действие не найдено')
    if result.verification_required:
        return result
    payload = decode_token(result.access_token)
    user = await db.get(User, UUID(payload['sub']))
    if action == 'register' and body.get('name'):
        if user.role == UserRole.candidate:
            await candidates.update_my_profile(CandidateProfileUpdate(first_name=body['name']), user, db)
        else:
            await save(db, user.id, 'company', {'representative': body['name']})
            await db.commit()
    set_cookie(response, result.access_token)
    return {'access_token': result.access_token, 'user': user_out(user)}

async def profile_view(db, profile, viewer, own=False, related=False):
    extra = await state(db, profile.user_id, 'profile')
    skills = (await db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == profile.id)
                              .options(selectinload(CandidateSkill.skill)))).scalars().all()
    category = await db.get(Category, profile.category_id) if profile.category_id else None
    contacts = None
    if own:
        owner = await db.get(User, profile.user_id)
        contacts = {'phone': profile.phone, 'email': owner.email}
        display = profile.first_name or ''
    elif related:
        from app.services.matching_service import display_name, contacts_for
        ep=await employer_profile(db,viewer.id)
        contacts=await contacts_for(db,ep.id,profile)
        display=display_name(profile,contacts is not None)
    else:
        public = await employers.preview_candidate(profile.id, viewer, db)
        display = public.display_name
        if not public.contacts_hidden: contacts = {'phone': public.phone, 'email': public.email}
    # Never return private extension fields through candidate discovery.
    permitted = {k: extra[k] for k in ('experience','salary','format','employment','languages','focus','work_experience') if k in extra}
    out = {'languages':' / '.join(profile.languages or []), 'employment':'Полная занятость', 'focus':'', **permitted, 'id': str(profile.id), 'name': display, 'surname': profile.last_name or '' if own else '',
           'patronymic': extra.get('patronymic','') if own else '', 'city': profile.city or '',
           'role': profile.headline or 'Специалист', 'about': profile.about or '',
           'format': extra.get('format', 'Удалённо' if profile.remote_ok else 'В офисе'),
           'experience': extra.get('experience','Без опыта'), 'salary': extra.get('salary',''),
           'tech': [s.skill.name for s in skills if s.skill], 'grade': category.label if category else 'Не подтверждён',
           'complete': extra.get('complete', profile.onboarding_completed), 'consent': extra.get('consent',False) if own else False,
           'initials': ''.join(n[0].upper() for n in display.split()[:2]), 'profile_strength': profile.profile_strength}
    if own: out.update({k:v for k,v in extra.items() if k not in ('id','grade','email','phone')}, id=str(profile.id), name=profile.first_name or '', surname=profile.last_name or '', tech=out['tech'], city=profile.city or '', role=profile.headline or 'Специалист', about=profile.about or '')
    if contacts:
        out.update(contacts)
        if extra.get('contact_email'): out['contact_email']=extra['contact_email']
        if extra.get('resume_file_id'):
            f = await state(db, profile.user_id, 'file:' + str(extra['resume_file_id']))
            out.update(resume=f.get('name',''), resume_file_id=extra['resume_file_id'], resume_url='/api/files/'+str(extra['resume_file_id']))
    else:
        for k in ('email','phone','resume','resume_file_id','resume_url'): out.pop(k,None)
    if extra.get('avatar_file_id'): out['photo'] = '/api/files/' + str(extra['avatar_file_id'])
    from app.services.reward_service import progress
    out['reward_level'] = (await progress(db, profile.user_id))['level']
    # The browser cannot mark registration complete independently of the server.
    out['complete'] = bool(profile.onboarding_completed)
    if own:
        from app.services.onboarding_service import registration_status
        out['registration'] = await registration_status(db, profile)
    return out

async def vacancy_view(db, vacancy, ep=None):
    if not ep: ep = await employer_profile(db, (await db.get(EmployerProfile, vacancy.employer_id)).user_id)
    extra = await state(db, ep.user_id, 'vacancy:' + str(vacancy.id))
    company = await state(db, ep.user_id, 'company')
    out = {'id': str(vacancy.id), 'employer_id': str(ep.id), 'title':vacancy.title, 'company':ep.company.name,
           'description':ep.company.description or '', 'website':ep.company.website or '', 'sector':ep.company.industry or '',
           'tech':vacancy.skills or [], 'salaryMin':str(vacancy.salary_min), 'salaryMax':str(vacancy.salary_max),
           'tasks':vacancy.description, 'published':vacancy.is_active, 'direction':'Backend', 'grade':'Middle',
           'city':'', 'format':FORMATS.get(vacancy.work_format.value if vacancy.work_format else 'remote','Удалённо'),
           'count':'1', 'experience':'От 3 лет', 'size':'', 'representative':'', 'position':'',
           'requirements':'', 'bonus':'', 'team':'', 'conditions':'', 'selection':'', 'test':'Без тестового задания', 'consent':False}
    if company.get('logo_file_id'):out['logo']='/api/files/'+company['logo_file_id']
    canonical=('id','employer_id','title','company','description','website','sector','tech','salaryMin','salaryMax','tasks','published','format')
    return {**out, **company, **extra, **{key:out[key] for key in canonical}}

@router.get('/api/vacancies/{vacancy_id}/candidate-matches')
async def vacancy_candidate_matches(vacancy_id: UUID, user=Depends(require_roles(UserRole.employer)), db=Depends(get_db)):
    from app.models.employer import EmployerNeed
    from app.services.matching_service import rank_candidates_for_need
    ep = await employer_profile(db, user.id)
    v = await vacancies._own_vacancy(db, ep, vacancy_id)
    view = await vacancy_view(db, v, ep)
    need = EmployerNeed(employer_id=ep.id, title=v.title,
        description='\n'.join(filter(None, [v.description, view.get('requirements')])),
        specialization_id=v.specialization_id, grade_id=v.grade_id,
        skills=v.skills or [], work_format=v.work_format)
    ranked = await rank_candidates_for_need(db, need, limit=100)
    for row in ranked:
        # Ranking does not compare cities or office/hybrid preferences.
        reasons = row['explanation']['reasons']
        row['explanation']['reasons'] = [r for r in reasons if r['code'] != 'FORMAT']
        if v.work_format and v.work_format.value == 'remote':
            row['explanation']['reasons'].append({'code': 'FORMAT', 'weight': 0, 'text': 'Удалённый формат работы подходит'})
    return {str(r['candidate'].id): {'match_score': r['match_score'], 'explanation': r['explanation']} for r in ranked}

async def active_vacancy(db, user):
    ep = await employer_profile(db, user.id)
    selected = (await state(db, user.id, 'settings')).get('active_vacancy_id')
    v = await db.get(Vacancy, UUID(selected)) if selected else None
    if not v or v.employer_id != ep.id:
        v = (await db.execute(select(Vacancy).where(Vacancy.employer_id==ep.id).order_by(Vacancy.created_at.desc()))).scalars().first()
    return ep, v

async def tasks_view(db, employer_id, vacancy_id):
    meta = await state(db, employer_id, 'taskset:' + str(vacancy_id), {'tasks': []})
    return meta.get('tasks', [])

async def invitation_tasks(db, inv, employer_user_id):
    sent = await state(db, employer_user_id, 'assessment-invitation:' + str(inv.id))
    return sent.get('tasks', []) if sent else await tasks_view(db, employer_user_id, inv.vacancy_id)

async def expire_company_assessment(db, inv, candidate_user_id, *, commit=True):
    await db.execute(select(Invitation.id).where(Invitation.id==inv.id).with_for_update())
    value = await state(db,candidate_user_id,'assessment:offer:'+str(inv.id))
    if value and not value.get('done') and value.get('deadlineAt',float('inf')) <= datetime.now(timezone.utc).timestamp()*1000:
        value={**value,'done':True,'result':{'status':'expired','completed':0},'submittedAt':datetime.now(timezone.utc).isoformat()}
        await save(db,candidate_user_id,'assessment:offer:'+str(inv.id),value)
        current=await state(db,candidate_user_id,'assessment:assignment')
        if current.get('offerId')==str(inv.id): await save(db,candidate_user_id,'assessment:assignment',value)
        from app.services.notification_service import notify
        ep=await db.get(EmployerProfile,inv.employer_id)
        await notify(db,ep.user_id,'assessment_failed','Соискатель не справился с тестовым',f'{inv.title}: время выполнения истекло.',{'url':'/employer/tasks'})
        await notify(db,candidate_user_id,'assessment_expired','Время тестового истекло','Тестовое не пройдено.',{'url':'/candidate/tasks'})
        if commit: await db.commit()
    return value

async def company_progress(db,inv,candidate_user_id):
    progress=await expire_company_assessment(db,inv,candidate_user_id)
    if not progress:return {}
    ep=await db.get(EmployerProfile,inv.employer_id)
    checks={}
    for index,t in enumerate(await invitation_tasks(db,inv,ep.user_id)):
        checked=await state(db,candidate_user_id,'practice:offer:'+str(inv.id)+':'+str(t['id']))
        if checked:checks[str(index)]={**checked['result'],'source_code':checked['source_code'],'language_id':checked.get('language_id')}
    return {**progress,'checks':checks}

@router.post('/api/offers/{offer_id}/assignment/start')
async def start_company_assignment(offer_id:UUID,user=Depends(candidate_only),db=Depends(get_db)):
    inv,_=await invitations._load(db,user,offer_id)
    if inv.status in (InvitationStatus.sent,InvitationStatus.viewed):
        await invitations._act(db,user,inv.id,'accepted','candidate')
    if inv.status!=InvitationStatus.accepted:raise HTTPException(409,'Приглашение недоступно')
    progress=await company_progress(db,inv,user.id)
    if not progress:
        await save_assessment('assignment',{'offerId':str(inv.id),'answers':{},'index':0,'done':False},user,db)
        progress=await company_progress(db,inv,user.id)
    await save(db,user.id,'assessment:assignment',progress);await db.commit()
    return progress

@router.get('/api/offers/{offer_id}/assignment')
async def get_company_assignment(offer_id:UUID,user=Depends(candidate_only),db=Depends(get_db)):
    inv,_=await invitations._load(db,user,offer_id)
    return await company_progress(db,inv,user.id)

async def offer_view(db, inv, user):
    from app.models.employer import EmployerProfile
    ep = await db.get(EmployerProfile, inv.employer_id)
    ep = await employer_profile(db,ep.user_id)
    v = await db.get(Vacancy, inv.vacancy_id) if inv.vacancy_id else None
    vd = await vacancy_view(db,v) if v else {'title':inv.title, 'company':ep.company.name, 'tech':[]}
    if not v:
        archived=await state(db,ep.user_id,'offer:archived-vacancy:'+str(inv.id))
        if archived: vd=archived
    logo=await state(db,ep.user_id,'company')
    if logo.get('logo_file_id'): vd['logo']='/api/files/'+logo['logo_file_id']
    person = await db.get(CandidateProfile, inv.candidate_id)
    p = await profile_view(db, person, user, own=user.id==person.user_id, related=True) if user.role==UserRole.employer else None
    progress = await company_progress(db,inv,person.user_id) if user.role==UserRole.candidate else await expire_company_assessment(db,inv,person.user_id)
    legacy = await state(db, person.user_id, 'assessment:assignment')
    submitted = bool(progress.get('done') or (legacy.get('offerId') == str(inv.id) and legacy.get('done')))
    sent_assessment = await state(db,ep.user_id,'assessment-invitation:'+str(inv.id))
    return {'id':str(inv.id), 'candidate_id':str(inv.candidate_id),'employer_id':str(inv.employer_id),
            'assessment_submitted':submitted,
            'hiring_stage':await state(db,ep.user_id,'hiring-stage:'+str(inv.id)),
            'assessment_progress':progress if user.role==UserRole.candidate else None,
            'assessment_attempt':sent_assessment.get('attempt_number',1),
            'previous_offer_id':sent_assessment.get('previous_offer_id'),
            'vacancy_id':str(inv.vacancy_id) if inv.vacancy_id else None,'company':vd.get('company',''), 'title':inv.title,
            'salary':f'{inv.salary_min}–{inv.salary_max}', 'format':vd.get('format',''), 'city':vd.get('city',''),
            'tech':vd.get('tech',[]), 'about':inv.message, 'date':inv.created_at.strftime('%d.%m.%Y %H:%M'),
            'status':{'sent':'new','viewed':'new','withdrawn':'declined','expired':'declined'}.get(inv.status.value,inv.status.value),
            'native_status':inv.status.value, 'vacancy':vd,'person':p,'logo':vd.get('logo'),
            'tasks':[{k:v for k,v in t.items() if user.role==UserRole.employer or k!='tests_json'} for t in await invitation_tasks(db, inv, ep.user_id)] if inv.vacancy_id else []}

def message_view(m,user):
    return {'id':m.id,'text':m.text,'sender_id':str(m.sender_id),'mine':m.sender_id==user.id,
            'client_message_id':m.client_message_id,'date':m.created_at.strftime('%H:%M')}

@router.get('/api/workspace')
async def workspace(user=Depends(get_current_user),db=Depends(get_db)):
    if await invitations.svc.expire_stale(db): await db.commit()
    result = {'user':user_out(user),'profile':{},'vacancy':{},'tasks':[],'people':[],'vacancies':[],'offers':[],
              'offerStatuses':{},'sent':[],'favorites':[], 'messages':{},'gradeTasks':[], 'assessment':None,
              'assignment':None,'generationFocus':{}}
    if user.role==UserRole.employer:
        from app.services.generation_billing import status as billing_status
        result['billing']=await billing_status(db,user.id)
        ep,v = await active_vacancy(db,user)
        mine = (await db.execute(select(Vacancy).where(Vacancy.employer_id==ep.id).order_by(Vacancy.created_at.desc()))).scalars().all()
        result['vacancies']=[await vacancy_view(db,row,ep) for row in mine]
        result['vacancy']=await vacancy_view(db,v,ep) if v else {'company':ep.company.name,'id':None,'title':'','tech':[],'published':False}
        result['tasks']=await tasks_view(db,user.id,v.id) if v else []
        people=(await db.execute(select(CandidateProfile).where(CandidateProfile.is_discoverable==True, CandidateProfile.onboarding_completed==True).limit(100))).scalars().all()
        result['people']=[await profile_view(db,p,user) for p in people]
        invs=(await db.execute(select(Invitation).where(Invitation.employer_id==ep.id).order_by(Invitation.created_at.desc()))).scalars().all()
        result['favorites']=(await state(db,user.id,'favorites',{'ids':[]})).get('ids',[])
        result['generationFocus']=await state(db,user.id,'generation-focus')
    elif user.role==UserRole.candidate:
        p=await candidate_profile(db,user.id)
        result['profile']=await profile_view(db,p,user,own=True)
        invs=(await db.execute(select(Invitation).where(Invitation.candidate_id==p.id).order_by(Invitation.created_at.desc()))).scalars().all()
        result['assessment']=await state(db,user.id,'assessment:grade') or None
        result['assignment']=await state(db,user.id,'assessment:assignment') or None
        if result['assignment'] and result['assignment'].get('offerId'):
            active=await db.get(Invitation,UUID(result['assignment']['offerId']))
            if active and active.candidate_id==p.id: result['assignment']=await company_progress(db,active,user.id) or result['assignment']
        result['gradeTasks']=(result['assessment'] or {}).get('questions',[])
    else: return result
    if user.role==UserRole.candidate: result['user']['name']=result['profile'].get('name') or user.email.split('@')[0]
    result['offers']=[await offer_view(db,i,user) for i in invs]
    result['offerStatuses']={o['id']:o['status'] for o in result['offers']}
    result['sent']=[o['candidate_id'] for o in result['offers'] if not v or o['vacancy_id']==str(v.id)] if user.role==UserRole.employer else []
    result['hidden_chat_ids']=[]
    deleted_chats={str(i.id):await state(db,user.id,'chat:deleted:'+str(i.id)) for i in invs}
    result['chat_deleted_until']={key:value.get('deleted_until',0) for key,value in deleted_chats.items()}
    if invs:
        rows=(await db.execute(select(ChatMessage).where(ChatMessage.offer_id.in_([i.id for i in invs])).order_by(ChatMessage.id))).scalars().all()
        for m in rows:
            if m.id>deleted_chats[str(m.offer_id)].get('deleted_until',0):result['messages'].setdefault(user.role.value+'-'+str(m.offer_id),[]).append(message_view(m,user))
        for i in invs:
            deleted=deleted_chats[str(i.id)]
            if deleted.get('hidden') and not result['messages'].get(user.role.value+'-'+str(i.id)):result['hidden_chat_ids'].append(str(i.id))
    return result

@router.get('/api/candidates/{candidate_id}')
async def candidate_detail(candidate_id:UUID,user=Depends(employer_only),db=Depends(get_db)):
    p=await db.get(CandidateProfile,candidate_id)
    if not p: raise HTTPException(404,'Профиль не найден')
    return await profile_view(db,p,user)

@router.post('/api/vacancies/search')
async def search_vacancies(body:dict,user=Depends(candidate_only),db=Depends(get_db)):
    from app.services.vacancy_search import rank
    query=str(body.get('query',''))[:300].strip()
    work_format=body.get('work_format')
    skill=str(body.get('skill','')).strip().lower()
    try: minimum=max(0,int(body.get('salary_min') or 0))
    except (ValueError,TypeError): raise HTTPException(422,'Проверьте минимальную зарплату')
    if work_format not in (None,'','remote','office','hybrid'): raise HTTPException(422,'Неизвестный формат работы')
    items=await vacancies.list_vacancies(db)
    options=sorted({skill for item in items for skill in item['skills']},key=str.lower)
    items=[item for item in items if (not work_format or item['work_format']==work_format) and
           (not minimum or item['salary_max']>=minimum) and (not skill or skill in [s.lower() for s in item['skills']])]
    ranked,method=await rank(query,items[:200])
    order=body.get('sort','relevance')
    if order=='salary': ranked.sort(key=lambda item:item['salary_max'],reverse=True)
    elif order=='recent': ranked.sort(key=lambda item:item['created_at'],reverse=True)
    elif order!='relevance': raise HTTPException(422,'Неизвестный порядок сортировки')
    return {'items':ranked,'total':len(ranked),'skills':options,'method':method}

@router.put('/api/me/profile')
async def update_profile(body:dict,user=Depends(candidate_only),db=Depends(get_db)):
    if 'work_experience' in body:
        body['work_experience']=validate_experience(body['work_experience'])
    p=await candidates.update_my_profile(CandidateProfileUpdate(first_name=body.get('name'),last_name=body.get('surname'),
        headline=body.get('role'),city=body.get('city'),phone=body.get('phone'),about=body.get('about'),
        remote_ok=body.get('format')!='В офисе',skills=body.get('tech')),user,db)
    stored=await state(db,user.id,'profile')
    # A form cannot overwrite server-owned upload identifiers or grades.
    extra={k:v for k,v in body.items() if k not in ('id','grade','photo','resume','resume_file_id','resume_url','avatar_file_id','email','resume_parse','complete','registration')}
    await save(db,user.id,'profile',{**stored,**extra})
    if body.get('complete') is True:
        from app.services.onboarding_service import complete_registration
        await complete_registration(db,p)
    await db.commit()
    return await profile_view(db,p,user,own=True)

@router.post('/api/me/registration/complete')
async def finish_registration(user=Depends(candidate_only),db=Depends(get_db)):
    from app.services.onboarding_service import complete_registration
    p=await candidate_profile(db,user.id)
    await complete_registration(db,p)
    await db.commit()
    return await profile_view(db,p,user,own=True)

def validate_experience(value):
    from app.services.resume_parser import WorkExperience
    from pydantic import ValidationError
    if not isinstance(value,list) or len(value)>30: raise HTTPException(422,'Можно указать до 30 мест работы')
    try: return [WorkExperience.model_validate(job).model_dump() for job in value]
    except ValidationError: raise HTTPException(422,'Проверьте поля опыта работы')

async def apply_resume_fields(db,user,parsed,replace=False):
    p=await candidate_profile(db,user.id)
    extra=await state(db,user.id,'profile')
    view=await profile_view(db,p,user,own=True)
    fields=parsed.get('fields',{})
    mapping={'name':'first_name','surname':'last_name','city':'city','phone':'phone','about':'about','role':'headline'}
    accepted={key:value for key,value in fields.items() if replace or not view.get(key) or (key=='role' and view[key]=='Специалист') or (key=='experience' and view[key]=='Без опыта')}
    native={mapping[key]:value for key,value in accepted.items() if key in mapping}
    if accepted.get('tech'):
        native['skills']=list(dict.fromkeys([*view.get('tech',[]),*accepted['tech']]))
        accepted['tech']=native['skills']
    p=await candidates.update_my_profile(CandidateProfileUpdate(**native),user,db)
    supplemental={key:value for key,value in accepted.items() if key not in mapping and key!='tech'}
    parsed={**parsed,'filled_fields':list(accepted),'skipped_fields':[key for key in fields if key not in accepted]}
    await save(db,user.id,'profile',{**extra,**supplemental,'resume_parse':parsed})
    return p

@router.post('/api/me/resume/apply')
async def apply_resume(user=Depends(candidate_only),db=Depends(get_db)):
    extra=await state(db,user.id,'profile')
    parsed=extra.get('resume_parse',{})
    if parsed.get('status')!='parsed': raise HTTPException(409,'Сначала загрузите PDF с текстовым резюме')
    p=await apply_resume_fields(db,user,parsed,replace=True)
    await db.commit()
    return await profile_view(db,p,user,own=True)

def salary(value):
    try: return int(str(value).replace(' ', '').replace('\u00a0',''))
    except (ValueError,TypeError): return 0

@router.post('/api/vacancies')
async def new_vacancy(user=Depends(employer_only),db=Depends(get_db)):
    ep=await employer_profile(db,user.id)
    v=Vacancy(employer_id=ep.id,title='Новая вакансия',description='',skills=[],salary_min=0,salary_max=0,is_active=False)
    db.add(v);await db.flush()
    await save(db,user.id,'settings',{'active_vacancy_id':str(v.id)});await db.commit()
    return {'id':str(v.id)}

@router.put('/api/me/active-vacancy')
async def select_vacancy(body:dict,user=Depends(employer_only),db=Depends(get_db)):
    ep=await employer_profile(db,user.id)
    v=await vacancies._own_vacancy(db,ep,UUID(body['vacancy_id']))
    await save(db,user.id,'settings',{'active_vacancy_id':str(v.id)});await db.commit();return {'ok':True}

@router.put('/api/me/vacancy')
async def update_vacancy(body:dict,user=Depends(employer_only),db=Depends(get_db)):
    ep,v=await active_vacancy(db,user)
    if body.get('id'):
        try: vid=UUID(str(body['id']))
        except ValueError: raise HTTPException(422,'Некорректный номер вакансии')
        v=await vacancies._own_vacancy(db,ep,vid)
    if not v:
        await new_vacancy(user,db);ep,v=await active_vacancy(db,user)
    spec=(await db.execute(select(Specialization).where(Specialization.code==body.get('direction','Backend').lower()))).scalar_one_or_none()
    grade=(await db.execute(select(Grade).where(Grade.code==body.get('grade','Middle').lower().replace('+','')))).scalar_one_or_none()
    values=dict(title=body.get('title',v.title) or 'Новая вакансия',description=body.get('tasks',v.description) or '',
        skills=body.get('tech',v.skills or []),salary_min=salary(body.get('salaryMin',v.salary_min)),salary_max=salary(body.get('salaryMax',v.salary_max)),
        specialization_id=(spec.id if spec else None) if 'direction' in body else v.specialization_id,
        grade_id=(grade.id if grade else None) if 'grade' in body else v.grade_id,
        work_format=next((k for k,val in FORMATS.items() if val==body.get('format')),'remote') if 'format' in body else (v.work_format.value if v.work_format else 'remote'))
    # Partial edits are autosaved independently of publication validation.
    publishing=bool(body.get('published') and not v.is_active)
    if publishing: validate_vacancy_publication(values)
    from app.models.employer import WorkFormat
    for k,val in values.items(): setattr(v,k,WorkFormat(val) if k=='work_format' else val)
    for field,key in (('name','company'),('description','description'),('website','website'),('industry','sector')):
        if key in body: setattr(ep.company,field,(body[key] or ep.company.name) if field=='name' else body[key])
    if publishing:
        v.is_active=True
        update_vacancy_trust(v,user)
    company={**await state(db,user.id,'company'),**{k:body[k] for k in ('representative','position','size') if k in body}}
    await save(db,user.id,'company',company)
    await save(db,user.id,'vacancy:'+str(v.id),{**await state(db,user.id,'vacancy:'+str(v.id)),**{k:val for k,val in body.items() if k not in ('id','employer_id','published')}})
    await db.commit();return await vacancy_view(db,v,ep)

def validate_vacancy_publication(values):
    problems=[]
    if not 3<=len(values['title'].strip())<=256:problems.append('Название вакансии: от 3 до 256 символов')
    if len(values['description'].strip())<10:problems.append('Задачи и обязанности: минимум 10 символов')
    if values['salary_min']<=0:problems.append('Зарплата «от»: укажите сумму больше нуля')
    if values['salary_max']<values['salary_min']:problems.append('Зарплата «до» должна быть не меньше зарплаты «от»')
    if problems:raise HTTPException(422,'Для публикации заполните поля: '+'. '.join(problems)+'.')
    return vacancies.VacancyCreate.model_validate(values)

def update_vacancy_trust(v,user):
    from app.domain.trust_rules import vacancy_trust
    age=(datetime.now(timezone.utc)-user.created_at).days if user.created_at else 365
    v.trust_score,v.trust_flags=vacancy_trust(salary_from=v.salary_min,salary_to=v.salary_max,text=f'{v.title}\n{v.description}',account_age_days=age)

@router.post('/api/me/vacancy/publish')
async def publish_vacancy(body:dict,user=Depends(employer_only),db=Depends(get_db)):
    ep=await employer_profile(db,user.id)
    try: vid=UUID(str(body.get('id','')))
    except ValueError:raise HTTPException(422,'Сначала сохраните вакансию')
    v=await vacancies._own_vacancy(db,ep,vid)
    await db.execute(select(Vacancy.id).where(Vacancy.id==v.id).with_for_update())
    await db.refresh(v)
    validate_vacancy_publication({'title':v.title,'description':v.description,'salary_min':v.salary_min,'salary_max':v.salary_max})
    view=await vacancy_view(db,v,ep)
    if not view.get('consent'):raise HTTPException(422,'Подтвердите согласие на публикацию вакансии')
    v.is_active=True
    update_vacancy_trust(v,user)
    await db.commit()
    return await vacancy_view(db,v,ep)

@router.put('/api/me/favorites')
async def favorites(body:list[str],user=Depends(employer_only),db=Depends(get_db)):
    for value in body:
        if not await db.get(CandidateProfile,UUID(value)): raise HTTPException(404,'Кандидат не найден')
    await save(db,user.id,'favorites',{'ids':body});await db.commit();return body

@router.post('/api/offers')
async def create_offer(body:dict,user=Depends(employer_only),db=Depends(get_db)):
    ep,v=await active_vacancy(db,user)
    if body.get('vacancy_id'): v=await vacancies._own_vacancy(db,ep,UUID(body['vacancy_id']))
    if not v or not v.is_active: raise HTTPException(409,'Сначала опубликуйте вакансию')
    inv=await invitations.create_invitation(InvitationCreate(candidate_id=UUID(body['candidate_id']),vacancy_id=v.id,
        title=v.title,message=v.description or 'Приглашаем обсудить вакансию в нашей команде.',
        salary_min=v.salary_min,salary_max=v.salary_max),user,db,None)
    return await offer_view(db,await db.get(Invitation,inv.id),user)

@router.get('/api/vacancies/{vacancy_id}/assessment-recipients')
async def assessment_recipients(vacancy_id:UUID,user=Depends(employer_only),db=Depends(get_db)):
    from app.services.task_recipients import eligible_candidate_ids
    ep=await employer_profile(db,user.id)
    await vacancies._own_vacancy(db,ep,vacancy_id)
    ids=await eligible_candidate_ids(db,ep.id,vacancy_id)
    rows=(await db.execute(select(CandidateProfile).where(CandidateProfile.id.in_(ids)))).scalars().all()
    from app.services.matching_service import display_name
    return [{'id':str(c.id),'name':display_name(c,False)} for c in rows]

@router.post('/api/vacancies/{vacancy_id}/assessment-invitations')
async def assessment_invitation(vacancy_id:UUID,body:dict,user=Depends(employer_only),db=Depends(get_db)):
    from app.services.task_recipients import eligible_candidate_ids
    ep=await employer_profile(db,user.id)
    v=await vacancies._own_vacancy(db,ep,vacancy_id)
    try: candidate_id=UUID(str(body.get('candidate_id','')))
    except ValueError: raise HTTPException(422,'Укажите соискателя')
    if candidate_id not in await eligible_candidate_ids(db,ep.id,v.id):
        raise HTTPException(403,'Тестовое можно отправить только откликнувшемуся соискателю или получателю вашего предложения по этой вакансии')
    from app.services.task_readiness import require_ready
    require_ready(await tasks_view(db,user.id,v.id))
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                     {'key':f'assessment-send:{v.id}:{candidate_id}'})
    inv=(await db.execute(select(Invitation).where(Invitation.employer_id==ep.id,Invitation.vacancy_id==v.id,Invitation.candidate_id==candidate_id).order_by(Invitation.created_at.desc()))).scalars().first()
    previous_offer_id=None
    attempt_number=1
    if inv:
        sent=await state(db,user.id,'assessment-invitation:'+str(inv.id))
        if sent:
            candidate=await db.get(CandidateProfile,candidate_id)
            progress=await expire_company_assessment(db,inv,candidate.user_id,commit=False)
            legacy=await state(db,candidate.user_id,'assessment:assignment')
            finished=progress.get('done') or (legacy.get('offerId')==str(inv.id) and legacy.get('done')) or inv.status in (InvitationStatus.expired,InvitationStatus.withdrawn,InvitationStatus.declined)
            if not finished:
                return {**await offer_view(db,inv,user),'assessment_created':False}
            previous_offer_id=str(inv.id)
            attempt_number=sent.get('attempt_number',1)+1
            inv=await invitations.svc.create_invitation(db,ep,user,{
                'candidate_id':candidate_id,'vacancy_id':v.id,'title':v.title,
                'message':v.description or 'Новая попытка тестового задания.',
                'salary_min':v.salary_min,'salary_max':v.salary_max},None,assessment_retry=True)
        elif inv.status not in (InvitationStatus.sent,InvitationStatus.viewed,InvitationStatus.accepted):
            inv=None
    if not inv:
        created = await create_offer({'candidate_id':str(candidate_id),'vacancy_id':str(v.id)},user,db)
        inv = await db.get(Invitation, UUID(created['id']))
    await db.execute(select(Invitation.id).where(Invitation.id == inv.id).with_for_update())
    key = 'assessment-invitation:' + str(inv.id)
    created_assessment=False
    if not await state(db, user.id, key):
        created_assessment=True
        from app.services.notification_service import notify
        candidate = await db.get(CandidateProfile, candidate_id)
        taskset = await tasks_view(db, user.id, v.id)
        from app.services.task_attempts import freeze_task
        frozen=[]
        for item in taskset:
            row=await db.get(EmployerTask,UUID(item['task_id'])) if item.get('task_id') else None
            if row and previous_offer_id:
                # TaskAssignment is unique per task/candidate: a retry needs a
                # separate task version so the previous submission stays intact.
                row=EmployerTask(employer_id=ep.id,title=row.title,statement=row.statement,
                    language=row.language,rubric=row.rubric or [],sources=row.sources or [],
                    origin=row.origin,specialization_id=row.specialization_id,grade_id=row.grade_id)
                db.add(row);await db.flush()
            frozen.append(await freeze_task(db,row,{**item,'vacancy_id':str(v.id)}) if row else {**item,'vacancy_id':str(v.id),'version':1})
        taskset=frozen
        await save(db, user.id, key, {'tasks': taskset, 'sent_at': datetime.now(timezone.utc).isoformat(),
                                    'attempt_number':attempt_number,'previous_offer_id':previous_offer_id})
        await notify(db, candidate.user_id, 'company_assessment', 'Новое тестовое задание',
            f'{ep.company.name} · {v.title} · заданий: {len(taskset)} · попытка {attempt_number}',
            {'url': '/candidate/tasks', 'offer_id': str(inv.id)})
        await db.commit()
    return {**await offer_view(db,inv,user),'assessment_created':created_assessment}

@router.put('/api/me/offer-statuses')
async def update_offer_statuses(body:dict,user=Depends(candidate_only),db=Depends(get_db)):
    for key,value in body.items():
        inv,_=await invitations._load(db,user,UUID(key))
        if value in ('accepted','declined') and inv.status.value!=value:
            await invitations._act(db,user,inv.id,value,'candidate')
    return body

@router.put('/api/me/tasks')
async def save_tasks(body:list[dict],user=Depends(employer_only),db=Depends(get_db)):
    ep,v=await active_vacancy(db,user)
    if not v: raise HTTPException(409,'Создайте вакансию')
    if len(body)>100 or len({t.get('id') for t in body})!=len(body): raise HTTPException(422,'До 100 заданий с уникальными номерами')
    old=await tasks_view(db,user.id,v.id)
    known={str(t.get('task_id')) for t in old if t.get('task_id')}
    for t in body:
        if str(t.get('practice_id','')).startswith('custom:'):
            t['practice_id']='custom:'+str(user.id)+':'+str(t['id'])
        if t.get('purpose')=='practice' and not t.get('practice_id'):
            t['practice_id']='custom:'+str(user.id)+':'+str(t['id'])
        if t.get('purpose') in ('hiring','qualification') and str(t.get('practice_id','')).startswith('custom:'):
            t.pop('practice_id',None)
        if not t.get('practice_id'):
            t['submission_format']='github' if t.get('purpose','hiring') in ('hiring','qualification') else 'text'
        else:t['submission_format']='code'
        if t.get('task_id') and str(t['task_id']) in known:
            row=await tasks._own_task(db,ep,UUID(t['task_id']))
            row.title=t['title'];row.statement=t.get('condition','') or t['title']
            row.language=t.get('language','python')
        else:
            row=EmployerTask(employer_id=ep.id,title=t['title'],statement=t.get('condition','') or t['title'],language=t.get('language','python'),rubric=t.get('rubric',[]),origin='rag' if t.get('sources') else 'authored')
            db.add(row);await db.flush();t['task_id']=str(row.id)
        from app.services.employer_task_service import normalize_rubric
        row.rubric=normalize_rubric(t.get('rubric',[]))
        row.sources=t.get('sources',[])
    remaining={str(t['task_id']) for t in body}
    for key in known-remaining:
        row=await tasks._own_task(db,ep,UUID(key));row.is_active=False
    await save(db,user.id,'taskset:'+str(v.id),{'tasks':body});await db.commit();return body

@router.post('/api/me/tasks/generate')
async def generate_tasks(body:dict=Body(default={}),user=Depends(employer_only),db=Depends(get_db)):
    from sqlalchemy import text as sql_text
    await db.execute(sql_text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'generate-task:'+str(user.id)})
    ep,v=await active_vacancy(db,user)
    if not v: raise HTTPException(409,'Создайте вакансию')
    target_id=body.get('replace_id')
    existing=await tasks_view(db,user.id,v.id)
    if target_id is not None and not any(str(t['id'])==str(target_id) for t in existing):
        raise HTTPException(404,'Задание для перегенерации не найдено')
    if target_id is None and len(existing)>=100:
        raise HTTPException(422,'Удалите лишние задания: максимум 100')
    text=' '.join(v.skills or []).lower()
    language=body.get('language') or ('java' if 'java' in text else 'sql' if 'sql' in text and 'python' not in text else 'python')
    grade=body.get('grade','middle'); purpose=body.get('purpose','hiring')
    if language not in (('python','java','javascript','cpp') if purpose=='practice' else ('python','java','sql')): raise HTTPException(422,'Этот язык не подходит для выбранного формата')
    if grade not in ('junior','middle','senior','lead') or purpose not in ('hiring','qualification','practice'): raise HTTPException(422,'Неверный формат задания')
    from app.services.generation_billing import require_credit,consume
    billing_row=await require_credit(db,user.id,purpose)
    from app.services import knowledge_service as ks
    from app.services.employer_task_service import draft_from_context
    focus=(await state(db,user.id,'generation-focus'))
    context=' '.join([v.title,v.description or '',text,str(body.get('focus') or focus.get('value',''))])[:6000]
    template=next((t for t in existing if str(t['id'])==str(target_id)),None) if target_id is not None else None
    base_id=body.get('base_id')
    base=next((t for t in existing if str(t['id'])==str(base_id)),None) if base_id is not None else (existing[-1] if existing else None)
    if base_id is not None and base is None: raise HTTPException(404,'Исходный шаблон не найден')
    excluded=[base['template_source']] if base and base.get('template_source') else (base.get('sources',[]) if base else [])
    if purpose=='practice':
        from app.services.algorithm_generation import generate as generate_algorithm
        history=await state(db,user.id,'generation:algorithm-history',{'counts':{}})
        counts=history.get('counts',{})
        task=await generate_algorithm(db,context=context,language=language,grade=grade,
            counts=counts,avoid_titles=[t['title'] for t in existing])
        source=task['template_source']
        await save(db,user.id,'generation:algorithm-history',{'counts':{**counts,source:counts.get(source,0)+1}})
    else:
        draft=await draft_from_context(db,language=language,grade=grade,context_text=context,purpose=purpose,template=template,exclude_sources=excluded if not template else None)
        task={'title':draft['title'],'condition':draft['statement'],'kind':'Проверка квалификации' if purpose=='qualification' else 'Практический кейс',
            'time':'45','points':'100','sample':'','criteria':'\n'.join(r['point'] for r in draft['rubric']),
            'purpose':purpose,'language':language,'rubric':draft['rubric'],'origin':'rag','sources':draft['sources'],'source_details':draft['source_details'],
            'generation_method':draft['generation_method'],'template_source':draft.get('template_source')}
    task['grade']=grade
    existing=await tasks_view(db,user.id,v.id)
    if target_id is not None:
        for index,previous in enumerate(existing):
            if str(previous['id'])==str(target_id):
                task['id']=previous['id']
                if previous.get('task_id'): task['task_id']=previous['task_id']
                existing[index]=task
                consume(billing_row,purpose)
                return await save_tasks(existing,user,db)
        raise HTTPException(404,'Задание было удалено во время генерации')
    task['id']=max((int(t['id']) for t in existing if str(t['id']).isdigit()),default=0)+1
    consume(billing_row,purpose)
    return await save_tasks([*existing,task],user,db)

@router.get('/api/me/generation-access')
async def generation_access(user=Depends(employer_only),db=Depends(get_db)):
    from app.services.generation_billing import status
    return await status(db,user.id)

class DemoTopupIn(BaseModel):
    units:int=Field(ge=1,le=10000,strict=True)
    request_id:UUID

@router.post('/api/me/generation-access/demo-topup')
async def generation_demo_topup(body:DemoTopupIn,user=Depends(employer_only),db=Depends(get_db)):
    from app.services.generation_billing import demo_topup
    return await demo_topup(db,user.id,body.units,body.request_id)

@router.get('/api/me/generator')
async def generator_status(user=Depends(employer_only)):
    from app.tasks.rag.llm import get_llm,NullLLM
    configured=not isinstance(get_llm(),NullLLM)
    return {'configured':configured,'provider':settings.llm_provider if configured else 'templates',
            'model':settings.gigachat_model if configured and settings.llm_provider=='gigachat' else None}

@router.put('/api/me/generation-focus')
async def focus(body:dict,user=Depends(employer_only),db=Depends(get_db)):
    await save(db,user.id,'generation-focus',body);await db.commit();return body

@router.post('/api/me/assessments/grade/start')
async def start_grade(user=Depends(candidate_only),db=Depends(get_db)):
    previous=await state(db,user.id,'assessment:grade')
    if previous and not previous.get('done'): return previous
    p=await candidate_profile(db,user.id)
    spec=await db.get(Specialization,p.specialization_id) if p.specialization_id else (await db.execute(select(Specialization).where(Specialization.code=='backend'))).scalar_one()
    grade=await db.get(Grade,p.declared_grade_id) if p.declared_grade_id else (await db.execute(select(Grade).where(Grade.code=='junior'))).scalar_one()
    session=await assessments.onboarding_start(OnboardingStartIn(specialization_id=spec.id,declared_grade_id=grade.id,languages=['python','sql']),user,db)
    questions=await assessments.session_questions(session.id,user,db)
    qs=[]
    for q in questions:
        options=(q.options or {}).get('choices',(q.options or {}).get('options',[]))
        qs.append({'id':str(q.id),'title':q.topic or q.prompt[:90], 'kind':q.kind or q.question_type,
                   'condition':q.prompt,'options':options,'question_type':q.question_type,'public':q.public,'time':'3','points':'1'})
    data={'session_id':str(session.id),'questions':qs,'startedAt':int(datetime.now(timezone.utc).timestamp()*1000),
          'answers':{},'index':0,'done':False,'duration':session.time_limit_s or 1200}
    await save(db,user.id,'assessment:grade',data);await db.commit();return data

@router.put('/api/me/assessments/{kind}')
async def save_assessment(kind:str,body:dict,user=Depends(candidate_only),db=Depends(get_db)):
    if kind not in ('grade','assignment'): raise HTTPException(404,'Тест не найден')
    prev=await state(db,user.id,'assessment:'+kind)
    if kind=='grade':
        if not prev: prev=await start_grade(user,db)
        data={**prev,**{k:body[k] for k in ('answers','index','done') if k in body}}
        if prev.get('done'): return prev
        answer_map={}
        for index,q in enumerate(prev['questions']):
            value=body.get('answers',{}).get(str(index))
            if value is not None:
                if q.get('kind')=='quiz_multi':
                    try: value=json.loads(value)
                    except (TypeError,ValueError): raise HTTPException(422,'Выберите варианты ответа')
                answer_map[q['id']]={'value':value}
                if not body.get('done'): await assessments.autosave(UUID(prev['session_id']),UUID(q['id']),AnswerIn(value=value),user,db)
        if body.get('done'):
            result=await assessments.session_submit(UUID(prev['session_id']),SubmitAnswersIn(answers=answer_map),user,db)
            data['result']={'grade':result.category_label or 'Не подтверждён','score':round(result.score*100),
                            'status':'reviewed','decision':result.decision_code,'next_step':result.next_step}
    else:
        inv,_=await invitations._load(db,user,UUID(str(body['offerId'])))
        await db.execute(select(Invitation.id).where(Invitation.id==inv.id).with_for_update())
        saved = await expire_company_assessment(db,inv,user.id)
        if saved.get('done') or (prev.get('offerId')==str(inv.id) and prev.get('done')):
            raise HTTPException(409,'Это тестовое уже отправлено. Повторная отправка недоступна.')
        if saved: prev=saved
        if inv.status!=InvitationStatus.accepted: raise HTTPException(403,'Сначала примите приглашение')
        ep=(await db.get(EmployerProfile,inv.employer_id))
        taskset=await invitation_tasks(db,inv,ep.user_id)
        if body.get('done') and not saved: raise HTTPException(409,'Сначала начните выполнение тестового')
        now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
        duration=sum(max(1,int(t.get('time') or 20)) for t in taskset)*60
        data={**saved,**{k:body[k] for k in ('offerId','answers','index','done') if k in body}}
        data.update(startedAt=saved.get('startedAt',now_ms),duration=saved.get('duration',duration),deadlineAt=saved.get('deadlineAt',now_ms+duration*1000))
        if body.get('done') and not (prev.get('done') and prev.get('offerId')==body.get('offerId')):
            p=await candidate_profile(db,user.id)
            for index,t in enumerate(taskset):
                answer=body.get('answers',{}).get(str(index),'')
                if answer.strip() and t.get('practice_id'):
                    checked=await state(db,user.id,'practice:offer:'+str(inv.id)+':'+str(t['id']))
                    result=checked.get('result',{})
                    if checked.get('source_code')!=answer or not result.get('total') or result.get('passed')!=result['total']:
                        raise HTTPException(422,'Для отправки алгоритма проверьте текущий код и пройдите все тесты')
            for index,t in enumerate(taskset):
                answer=body.get('answers',{}).get(str(index),'')
                if not answer.strip():
                    previous=(await db.execute(select(TaskAssignment).where(TaskAssignment.task_id==UUID(t['task_id']),TaskAssignment.candidate_id==p.id))).scalar_one_or_none() if t.get('task_id') else None
                    if previous and previous.status=='assigned':previous.status='skipped'
                    continue
                row=await db.get(EmployerTask,UUID(t['task_id']))
                if not row or row.employer_id!=ep.id: raise HTTPException(404,'Задание не найдено')
                a=(await db.execute(select(TaskAssignment).where(TaskAssignment.task_id==row.id,TaskAssignment.candidate_id==p.id))).scalar_one_or_none()
                if not a: a=TaskAssignment(task_id=row.id,candidate_id=p.id);db.add(a);await db.flush()
                from app.services.task_attempts import freeze_assignment
                await freeze_assignment(db,a,user.id,{**t,'offer_id':str(inv.id)})
                if t.get('practice_id'):
                    checked=await state(db,user.id,'practice:offer:'+str(inv.id)+':'+str(t['id']))
                    if checked.get('source_code')!=answer: raise HTTPException(422,'Проверьте текущее решение алгоритма перед отправкой')
                    result=checked.get('result',{})
                    if not result.get('total') or result.get('passed')!=result['total']: raise HTTPException(422,'Для отправки алгоритма пройдите все проверочные тесты')
                if a.status=='assigned':
                    if t.get('practice_id'):
                        a.answer,a.status,a.submitted_at=answer,'submitted',datetime.now(timezone.utc)
                        a.auto_score=checked['result']['passed']/checked['result']['total']
                        from app.services.employer_task_service import _update_task_ratio
                        await _update_task_ratio(db,p,a.auto_score)
                    elif not t.get('practice_id'):
                        await save(db,user.id,'assignment:clock:'+str(a.id),{'startedAt':data['startedAt'],'duration':data['duration'],'deadlineAt':data['deadlineAt']})
                        from app.api.v1.tasks import submit_task, SubmitIn
                        await submit_task(a.id,SubmitIn(repo_url=answer.strip()),user,db)
                if t.get('practice_id'):
                    data.setdefault('executions',{})[str(index)]=checked['result']
        data['result']={'status':'submitted'} if data.get('done') else None
        if data.get('done'):
            from app.services.notification_service import notify
            count=sum(bool(str(a).strip()) for a in data.get('answers',{}).values())
            data['submittedAt']=datetime.now(timezone.utc).isoformat()
            await notify(db,ep.user_id,'assessment_submitted' if count else 'assessment_failed',
                'Соискатель отправил тестовое' if count else 'Соискатель не справился с тестовым',
                f'{inv.title}: отправлено решений {count} из {len(taskset)}.',{'url':'/employer/tasks?offer='+str(inv.id) if count else '/employer/tasks','offer_id':str(inv.id)})
            if not count: await save(db,ep.user_id,'assessment:failure-notified:'+str(inv.id),{'sent':True})
    if kind=='assignment': await save(db,user.id,'assessment:offer:'+str(inv.id),data)
    await save(db,user.id,'assessment:'+kind,data);await db.commit();return data

@router.get('/api/offers/{offer_id}/assessment')
async def offer_assessment(offer_id:UUID,user=Depends(employer_only),db=Depends(get_db)):
    inv,_=await invitations._load(db,user,offer_id)
    p=await db.get(CandidateProfile,inv.candidate_id)
    value=await expire_company_assessment(db,inv,p.user_id) or await state(db,p.user_id,'assessment:assignment')
    if value.get('offerId')!=str(inv.id): return None
    taskset=await invitation_tasks(db,inv,user.id)
    ids=[UUID(t['task_id']) for t in taskset]
    rows=(await db.execute(select(TaskAssignment).where(TaskAssignment.candidate_id==p.id,TaskAssignment.task_id.in_(ids)))).scalars().all()
    value['repository_reports']=[{'title':t['title'],'status':a.status,'report':a.eval_details} for a in rows for t in taskset if str(a.task_id)==t['task_id'] and a.eval_details]
    return value

@router.get('/api/employer/submissions')
async def company_submissions(user=Depends(employer_only),db=Depends(get_db)):
    ep=await employer_profile(db,user.id)
    invs=(await db.execute(select(Invitation).where(Invitation.employer_id==ep.id).order_by(Invitation.created_at.desc()))).scalars().all()
    output=[]
    included=set()
    for inv in invs:
        person=await db.get(CandidateProfile,inv.candidate_id)
        progress=await expire_company_assessment(db,inv,person.user_id)
        if not progress:
            legacy=await state(db,person.user_id,'assessment:assignment')
            if legacy.get('offerId')==str(inv.id): progress=legacy
        if not progress.get('done') or progress.get('result',{}).get('status')=='expired': continue
        taskset=await invitation_tasks(db,inv,user.id)
        ids=[UUID(t['task_id']) for t in taskset if t.get('task_id')]
        rows=(await db.execute(select(TaskAssignment).where(TaskAssignment.candidate_id==person.id,TaskAssignment.task_id.in_(ids)))).scalars().all()
        included.update(a.id for a in rows)
        if inv.status == InvitationStatus.withdrawn: continue
        by_id={str(a.task_id):a for a in rows}
        from app.services.task_attempts import evaluation_status
        details=[];completed=0;pending=0
        for index,t in enumerate(taskset):
            a=by_id.get(str(t.get('task_id')))
            execution=progress.get('executions',{}).get(str(index))
            code=progress.get('answers',{}).get(str(index),'')
            if not t.get('practice_id') and a and a.answer:code=a.answer
            solved=bool(execution and execution.get('total') and execution.get('passed')==execution['total']) if t.get('practice_id') else bool(a and (a.reviewer_score if a.reviewer_score is not None else a.auto_score or 0)>=0.7)
            completed+=int(solved)
            pending+=int(bool(a and evaluation_status(a) in ('checking','unavailable','awaiting_employer')))
            details.append({'title':t['title'],'condition':t.get('condition'),'algorithm':bool(t.get('practice_id')),'answer':code or (a.answer if a else ''),'execution':execution,'git_report':a.eval_details if a else None,'assignment_id':str(a.id) if a else None,'status':a.status if a else 'not_submitted','evaluation_status':evaluation_status(a) if a else 'not_submitted','score':(a.reviewer_score if a.reviewer_score is not None else a.auto_score) if a else None,'solved':solved})
        has_repository = any(not item["algorithm"] and item["answer"] for item in details)
        if not completed and not pending and not has_repository:
            key='assessment:failure-notified:'+str(inv.id)
            if not await state(db,user.id,key):
                from app.services.notification_service import notify
                await notify(db,user.id,'assessment_failed','Соискатель не справился с тестовым',f'{inv.title}: выполнено 0 из {len(taskset)} заданий.',{'url':'/employer/tasks'})
                await save(db,user.id,key,{'sent':True});await db.commit()
            continue
        from app.services.matching_service import display_name
        vacancy=await db.get(Vacancy,inv.vacancy_id) if inv.vacancy_id else None
        output.append({'id':str(inv.id),'candidate':display_name(person,True),'vacancy':vacancy.title if vacancy else inv.title,'company':ep.company.name,'completed':completed,'total':len(taskset),'pending':pending,'submitted_at':progress.get('submittedAt'),'duration':progress.get('duration'),'elapsed_seconds':max(0,(datetime.fromisoformat(progress['submittedAt']).timestamp()*1000-progress['startedAt'])/1000) if progress.get('submittedAt') else None,'tasks':details})
    standalone=(await db.execute(select(TaskAssignment,EmployerTask,CandidateProfile).join(EmployerTask,EmployerTask.id==TaskAssignment.task_id).join(CandidateProfile,CandidateProfile.id==TaskAssignment.candidate_id).where(EmployerTask.employer_id==ep.id,TaskAssignment.status.in_(['submitted','reviewed','evaluating'])))).all()
    for a,t,c in standalone:
        if a.id in included: continue
        from app.services.task_attempts import assignment_version,evaluation_status
        from app.services.matching_service import display_name
        meta=await assignment_version(db,a,t)
        score=a.reviewer_score if a.reviewer_score is not None else a.auto_score
        execution=(a.eval_details or {}).get('execution')
        solved=bool(execution and execution.get('total') and execution.get('passed')==execution['total']) if meta.get('practice_id') else bool(score is not None and score>=.7)
        pending=int(evaluation_status(a) in ('checking','unavailable','awaiting_employer'))
        if not solved and not pending and not (not meta.get("practice_id") and a.answer):
            key='assessment:failure-notified:assignment:'+str(a.id)
            if not await state(db,user.id,key):
                from app.services.notification_service import notify
                await notify(db,user.id,'assessment_failed','Соискатель не справился с тестовым',f'{t.title}: выполнено 0 из 1 задания.',{'url':'/employer/tasks'})
                await save(db,user.id,key,{'sent':True});await db.commit()
            continue
        output.append({'id':'assignment:'+str(a.id),'candidate':display_name(c,True),'vacancy':meta.get('vacancy_title') or 'Вакансия не указана','vacancy_id':meta.get('vacancy_id'),'company':ep.company.name,'completed':int(solved),'total':1,'pending':pending,'duration':max(1,int(meta.get('time') or 20))*60,'elapsed_seconds':None,'submitted_at':a.submitted_at.isoformat() if a.submitted_at else None,'tasks':[{'title':meta['title'],'condition':meta['condition'],'algorithm':bool(meta.get('practice_id')),'answer':a.answer or '', 'execution':execution,'git_report':a.eval_details if not meta.get('practice_id') else None,'assignment_id':str(a.id),'status':a.status,'evaluation_status':evaluation_status(a),'score':score,'solved':solved}]})
    for item in output:
        review = await state(db,user.id,'submission:reviewed:'+item['id'])
        item['review_status'] = 'reviewed' if review else 'pending'
        item['reviewed_at'] = review.get('reviewed_at')
        if not item['id'].startswith('assignment:'):
            invitation=await db.get(Invitation,UUID(item['id']))
            item['offer_id']=item['id']
            item['native_status']=invitation.status.value
            item['hiring_stage']=await state(db,user.id,'hiring-stage:'+item['id'])
    await db.commit()
    return output

@router.post('/api/employer/submissions/{submission_id}/reviewed')
async def mark_submission_reviewed(submission_id:str,user=Depends(employer_only),db=Depends(get_db)):
    reports=await company_submissions(user,db)
    if not any(item['id']==submission_id for item in reports):
        raise HTTPException(404,'Решение не найдено или предложение отозвано')
    key='submission:reviewed:'+submission_id
    review=await state(db,user.id,key)
    if not review:
        review={'reviewed_at':datetime.now(timezone.utc).isoformat()}
        await save(db,user.id,key,review)
        await db.commit()
    return {'review_status':'reviewed',**review}

@router.post('/api/offers/{offer_id}/stage')
async def advance_hiring_stage(offer_id:UUID,body:dict,user=Depends(employer_only),db=Depends(get_db)):
    inv,_=await invitations._load(db,user,offer_id)
    await db.refresh(inv,with_for_update=True)
    if inv.status not in (InvitationStatus.sent,InvitationStatus.viewed,InvitationStatus.accepted):
        raise HTTPException(409,'Предложение закрыто — переход на новый этап недоступен')
    person=await db.get(CandidateProfile,inv.candidate_id)
    progress=await expire_company_assessment(db,inv,person.user_id,commit=False)
    if not progress.get('done') or progress.get('result',{}).get('status')=='expired':
        sent=await state(db,user.id,'assessment-invitation:'+str(inv.id))
        accepted_application=await db.scalar(select(Application.id).where(Application.candidate_id==inv.candidate_id,Application.vacancy_id==inv.vacancy_id,Application.status==ApplicationStatus.accepted))
        if sent or not accepted_application:
            raise HTTPException(409,'Сначала дождитесь отправки тестового задания или примите отклик соискателя')
    stage=body.get('stage');message=body.get('message','')
    if not isinstance(stage,str) or not 2<=len(stage.strip())<=100 or not isinstance(message,str) or len(message)>2000:
        raise HTTPException(422,'Укажите название этапа (2–100 символов), сообщение — до 2000 символов')
    stage=stage.strip();message=message.strip()
    key='hiring-stage:'+str(inv.id)
    previous=await state(db,user.id,key)
    if previous.get('name')==stage and previous.get('message')==message: return previous
    value={'name':stage,'message':message,'updated_at':datetime.now(timezone.utc).isoformat(),
           'history':(previous.get('history',[])+[{'name':stage,'message':message,'at':datetime.now(timezone.utc).isoformat()}])[-100:]}
    await save(db,user.id,key,value)
    row=ChatMessage(offer_id=inv.id,sender_id=user.id,text='Вы переходите на новый этап: '+stage+'.'+(('\n'+message) if message else ''))
    db.add(row)
    from app.services.notification_service import notify
    await notify(db,person.user_id,'hiring_stage','Вы приглашены на новый этап',stage,
                 {'url':'/candidate/chat/'+str(inv.id),'offer_id':str(inv.id),'stage':stage})
    await db.commit();await db.refresh(row)
    await chat_hub.publish(str(inv.id),{'type':'message','message':message_view(row,user)})
    return value

@router.delete('/api/me/vacancies/{vacancy_id}')
async def delete_owned_vacancy(vacancy_id:UUID,user=Depends(employer_only),db=Depends(get_db)):
    from sqlalchemy import delete
    ep=await employer_profile(db,user.id)
    v=await vacancies._own_vacancy(db,ep,vacancy_id)
    await db.refresh(v,with_for_update=True)
    from app.models.vacancy import ArchivedVacancy
    snapshot=await vacancy_view(db,v,ep)
    company=await state(db,user.id,'company')
    if company.get('logo_file_id'):snapshot['logo']='/api/files/'+company['logo_file_id']
    applications=(await db.execute(select(Application).where(Application.vacancy_id==v.id))).scalars().all()
    db.add(ArchivedVacancy(id=v.id,employer_id=ep.id,snapshot={'vacancy':snapshot,'applications':[{'id':str(a.id),'candidate_id':str(a.candidate_id),'status':a.status.value,'cover_letter':a.cover_letter} for a in applications],'taskset':await state(db,user.id,'taskset:'+str(v.id))}))
    related=(await db.execute(select(Invitation).where(Invitation.vacancy_id==v.id))).scalars().all()
    for inv in related:
        await save(db,user.id,'offer:archived-vacancy:'+str(inv.id),snapshot)
        if inv.status in (InvitationStatus.sent,InvitationStatus.viewed,InvitationStatus.accepted):
            await invitations.svc.transition(db,inv,'withdrawn','employer',user.id)
        inv.vacancy_id=None
    await db.flush()
    await db.execute(delete(Application).where(Application.vacancy_id==v.id))
    await db.execute(delete(EndpointState).where(EndpointState.user_id==user.id,EndpointState.key.in_(['vacancy:'+str(v.id),'taskset:'+str(v.id),'ats:vacancy:'+str(v.id)])))
    await db.delete(v);await db.commit()
    return {'ok':True}

@router.delete('/api/offers/{offer_id}/chat')
async def delete_own_chat(offer_id:UUID,user=Depends(get_current_user),db=Depends(get_db)):
    await invitations._load(db,user,offer_id)
    maximum=await db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.offer_id==offer_id)) or 0
    await save(db,user.id,'chat:deleted:'+str(offer_id),{'hidden':True,'deleted_until':maximum})
    await save(db,user.id,'chat:read:'+str(offer_id),{'last_id':maximum})
    await db.commit();return {'ok':True}

@router.post('/api/offers/{offer_id}/chat/restore')
async def restore_own_chat(offer_id:UUID,user=Depends(get_current_user),db=Depends(get_db)):
    await invitations._load(db,user,offer_id)
    key='chat:deleted:'+str(offer_id)
    previous=await state(db,user.id,key)
    if previous:await save(db,user.id,key,{**previous,'hidden':False});await db.commit()
    return {'ok':True}

@router.delete('/api/me/account')
async def delete_own_account(body:dict,user=Depends(get_current_user),db=Depends(get_db)):
    from sqlalchemy import delete
    from app.core.security import verify_password,hash_password
    from app.models.platform import Notification
    import secrets
    if not isinstance(body.get('password'),str) or not verify_password(body['password'],user.password_hash):
        raise HTTPException(403,'Введите текущий пароль для удаления аккаунта')
    await db.refresh(user,with_for_update=True)
    if user.role==UserRole.candidate:
        p=await candidate_profile(db,user.id)
        p.first_name='Удалённый';p.last_name='пользователь';p.phone=None;p.city=None;p.headline=None;p.about=None;p.search_text=None;p.embedding=None;p.privacy={};p.is_discoverable=False;p.onboarding_completed=False
        related=(await db.execute(select(Invitation).where(Invitation.candidate_id==p.id))).scalars().all()
        await db.execute(delete(Application).where(Application.candidate_id==p.id))
    elif user.role==UserRole.employer:
        ep=await employer_profile(db,user.id);ep.position=None;ep.contact_phone=None
        owned=(await db.execute(select(Vacancy).where(Vacancy.employer_id==ep.id))).scalars().all()
        for v in owned:v.is_active=False
        related=(await db.execute(select(Invitation).where(Invitation.employer_id==ep.id))).scalars().all()
    else:related=[]
    for inv in related:
        if inv.status in (InvitationStatus.sent,InvitationStatus.viewed,InvitationStatus.accepted):
            if user.role==UserRole.candidate:
                from app.models.platform import InvitationEvent
                old=inv.status.value;inv.status=InvitationStatus.withdrawn;inv.decided_at=datetime.now(timezone.utc)
                db.add(InvitationEvent(invitation_id=inv.id,from_status=old,to_status='withdrawn',actor='system',actor_user_id=user.id))
                db.add(ChatMessage(offer_id=inv.id,sender_id=user.id,text='Аккаунт соискателя удалён. Переписка закрыта.'))
            else:await invitations.svc.transition(db,inv,'withdrawn','employer',user.id)
    await db.execute(delete(EndpointState).where(EndpointState.user_id==user.id))
    await db.execute(delete(Notification).where(Notification.user_id==user.id))
    user.email=str(user.id)+'@deleted.invalid';user.password_hash=hash_password(secrets.token_urlsafe(48));user.is_active=False
    await db.commit();return {'ok':True}

@router.get('/api/me/drafts/{key}')
async def draft(key:str,user=Depends(get_current_user),db=Depends(get_db)):
    return await state(db,user.id,'draft:'+key)

@router.put('/api/me/drafts/{key}')
async def save_draft(key:str,body:dict,user=Depends(get_current_user),db=Depends(get_db)):
    if len(key)>100 or len(json.dumps(body))>600000: raise HTTPException(413,'Черновик слишком большой')
    await save(db,user.id,'draft:'+key,body);await db.commit();return body

@router.post('/api/me/files/{kind}')
async def upload(kind:str,file:UploadFile=File(...),user=Depends(get_current_user),db=Depends(get_db)):
    if kind=='logo':
        if user.role!=UserRole.employer: raise HTTPException(403,'Логотип доступен работодателю')
    elif user.role!=UserRole.candidate: raise HTTPException(403,'Файл доступен соискателю')
    if kind not in ('avatar','resume','logo'): raise HTTPException(404,'Тип файла не найден')
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,'Максимум 10 МБ')
    if kind in ('avatar','logo'):
        import io
        from PIL import Image, UnidentifiedImageError
        Image.MAX_IMAGE_PIXELS=10_000_000
        try:
            image=Image.open(io.BytesIO(content));image.load();out=io.BytesIO();image.convert('RGB').save(out,format='JPEG');content=out.getvalue()
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError): raise HTTPException(422,'Выберите корректное изображение')
        mime='image/jpeg'
    else:
        ext=Path(file.filename or '').suffix.lower()
        mime={'.pdf':'application/pdf','.doc':'application/msword','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}.get(ext)
        valid=bool(mime) and ((ext=='.pdf' and content.startswith(b'%PDF-')) or
            (ext=='.doc' and content.startswith(bytes.fromhex('D0CF11E0A1B11AE1'))) or
            (ext=='.docx' and zipfile.is_zipfile(io.BytesIO(content))))
        if valid and ext=='.docx':
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                valid='[Content_Types].xml' in archive.namelist() and 'word/document.xml' in archive.namelist()
        if not valid: raise HTTPException(422,'Выберите корректный PDF, DOC или DOCX')
    key=str(uuid4());(UPLOADS/key).write_bytes(content)
    await save(db,user.id,'file:'+key,{'kind':kind,'name':Path(file.filename or 'file').name,'mime':mime,'storage_key':key})
    storage='company' if kind=='logo' else 'profile'
    p=await state(db,user.id,storage);await save(db,user.id,storage,{**p,kind+'_file_id':key})
    if kind=='resume':
        from app.services.resume_parser import parse_pdf_file
        parsed=await parse_pdf_file(UPLOADS/key) if mime=='application/pdf' else {'status':'unsupported','message':'Автозаполнение доступно для PDF с текстом.','fields':{}}
        await apply_resume_fields(db,user,parsed)
    await db.commit()
    if kind=='logo':return {'logo':'/api/files/'+key}
    return await profile_view(db,await candidate_profile(db,user.id),user,own=True)

@router.get('/api/files/{file_id}')
async def private_file(file_id:UUID,user=Depends(get_current_user),db=Depends(get_db)):
    row=(await db.execute(select(EndpointState).where(EndpointState.key=='file:'+str(file_id)))).scalar_one_or_none()
    if not row: raise HTTPException(404,'Файл не найден')
    if row.user_id!=user.id and row.data['kind']!='logo':
        if user.role!=UserRole.employer: raise HTTPException(404,'Файл не найден')
        p=await candidate_profile(db,row.user_id)
        public=await employers.preview_candidate(p.id,user,db)
        if row.data['kind']=='resume' and public.contacts_hidden: raise HTTPException(404,'Файл не найден')
    path=UPLOADS/row.data['storage_key']
    if not path.is_file(): raise HTTPException(404,'Файл не найден')
    return FileResponse(path,media_type=row.data['mime'],filename=row.data['name'],content_disposition_type='inline' if row.data['kind'] in ('avatar','logo') or row.data['mime']=='application/pdf' else 'attachment',headers={'X-Content-Type-Options':'nosniff'})

async def judge(path,method='GET',body=None):
    try:
        async with httpx.AsyncClient(timeout=20,trust_env=False) as c:
            r=await c.request(method,os.environ['JUDGE0_URL'].rstrip('/')+path,json=body,
                              headers={'X-Auth-Token':os.getenv('JUDGE0_AUTH_TOKEN','')})
            r.raise_for_status();return r.json()
    except (httpx.HTTPError,ValueError,KeyError): raise HTTPException(503,'Judge0 временно недоступен')

@router.get('/api/config')
async def config(user=Depends(get_current_user)):
    try: await judge('/languages');return {'configured':True,'connected':True}
    except HTTPException: return {'configured':True,'connected':False}

class Submission(BaseModel):
    source_code:str=Field(min_length=1,max_length=100000)
    stdin:str=Field(default='',max_length=20000)
    language_id:int

@router.post('/api/submissions')
async def run_code(body:Submission,user=Depends(get_current_user),db=Depends(get_db)):
    if body.language_id not in (63,71,54,62): raise HTTPException(422,'Неподдерживаемый язык')
    data=await judge('/submissions?base64_encoded=true&wait=false','POST',
        {'source_code':base64.b64encode(body.source_code.encode()).decode(),'stdin':base64.b64encode(body.stdin.encode()).decode(),
         'language_id':body.language_id,'cpu_time_limit':5,'wall_time_limit':10,'memory_limit':128000,'enable_network':False})
    await save(db,user.id,'submission:'+data['token'],{'created_at':datetime.now(timezone.utc).isoformat()});await db.commit();return data

@router.get('/api/submissions/{token}')
async def execution_result(token:UUID,user=Depends(get_current_user),db=Depends(get_db)):
    if not await state(db,user.id,'submission:'+str(token)): raise HTTPException(404,'Запуск не найден')
    data=await judge(f'/submissions/{token}?base64_encoded=true&fields=stdout,stderr,compile_output,message,status,time,memory,exit_code')
    for k in ('stdout','stderr','compile_output','message'):
        if data.get(k): data[k]=base64.b64decode(data[k]).decode('utf-8',errors='replace')
    return data

class MessageIn(BaseModel):
    text:str=Field(min_length=1,max_length=10000)
    client_message_id:UUID|None=None
    @field_validator('text')
    @classmethod
    def nonempty(cls,value):
        value=value.strip()
        if not value: raise ValueError('Пустое сообщение')
        return value

async def persist_message(db,inv,user,body):
    if inv.status in (InvitationStatus.declined,InvitationStatus.expired,InvitationStatus.withdrawn):
        raise HTTPException(403,'Переписка закрыта')
    key=str(body.client_message_id) if body.client_message_id else None
    async def existing():
        return (await db.execute(select(ChatMessage).where(ChatMessage.offer_id==inv.id,ChatMessage.sender_id==user.id,
                                                          ChatMessage.client_message_id==key))).scalar_one_or_none()
    if key:
        row=await existing()
        if row: return row
    count=await db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.sender_id==user.id,
                            ChatMessage.created_at>datetime.now(timezone.utc)-timedelta(minutes=1)))
    if count>=30: raise HTTPException(429,'Не более 30 сообщений в минуту')
    row=ChatMessage(offer_id=inv.id,sender_id=user.id,text=body.text,client_message_id=key)
    db.add(row)
    try: await db.commit();await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        if not key: raise
        row=await existing()
        if not row: raise
    return row

@router.get('/api/offers/{offer_id}/messages')
async def history(offer_id:UUID,user=Depends(get_current_user),db=Depends(get_db)):
    await invitations._load(db,user,offer_id)
    rows=(await db.execute(select(ChatMessage).where(ChatMessage.offer_id==offer_id).order_by(ChatMessage.id))).scalars().all()
    deleted=await state(db,user.id,'chat:deleted:'+str(offer_id))
    return [message_view(m,user) for m in rows if m.id>deleted.get('deleted_until',0)]

@router.get('/api/messages/unread')
async def unread_messages(user=Depends(get_current_user),db=Depends(get_db)):
    from sqlalchemy import Integer
    if user.role == UserRole.employer:
        ep=await employer_profile(db,user.id)
        access=Invitation.employer_id==ep.id
    elif user.role == UserRole.candidate:
        candidate=await candidate_profile(db,user.id)
        access=Invitation.candidate_id==candidate.id
    else: raise HTTPException(403,'Недоступно для этой роли')
    checkpoint=func.coalesce(EndpointState.data['last_id'].astext.cast(Integer),0)
    count=await db.scalar(select(func.count(ChatMessage.id)).join(Invitation,Invitation.id==ChatMessage.offer_id)
        .outerjoin(EndpointState,(EndpointState.user_id==user.id)&(EndpointState.key==func.concat('chat:read:',Invitation.id)))
        .where(access,ChatMessage.sender_id!=user.id,ChatMessage.id>checkpoint))
    return {'unread':count or 0}

@router.post('/api/offers/{offer_id}/messages/read')
async def read_messages(offer_id:UUID,body:dict,user=Depends(get_current_user),db=Depends(get_db)):
    from sqlalchemy import text
    await invitations._load(db,user,offer_id)
    last_id=body.get('last_id')
    maximum=await db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.offer_id==offer_id)) or 0
    if type(last_id) is not int or not 0<=last_id<=maximum: raise HTTPException(422,'Некорректное сообщение')
    await db.execute(text("INSERT INTO endpoint_ui_state (user_id,key,data) VALUES (:user_id,:key,jsonb_build_object('last_id',CAST(:last_id AS integer))) ON CONFLICT (user_id,key) DO UPDATE SET data=jsonb_build_object('last_id',GREATEST(COALESCE((endpoint_ui_state.data->>'last_id')::integer,0),CAST(:last_id AS integer)))"),{'user_id':user.id,'key':'chat:read:'+str(offer_id),'last_id':last_id})
    await db.commit()
    return {'ok':True}

@router.websocket('/ws/offers/{offer_id}')
async def chat_socket(websocket:WebSocket,offer_id:UUID):
    protocols=websocket.scope.get('subprotocols',[])
    token=next((p.removeprefix('endpoint.bearer.') for p in protocols if p.startswith('endpoint.bearer.')),None)
    if websocket.headers.get('origin') not in settings.cors_origin_list or 'endpoint.chat.v1' not in protocols:
        await websocket.close(code=4403);return
    # Accept first so the browser receives application close codes (otherwise HTTP 403 hides them).
    await websocket.accept(subprotocol='endpoint.chat.v1')
    async def identity(db):
        if not token: raise HTTPException(401,'Сессия истекла')
        return await get_current_user(db,HTTPAuthorizationCredentials(scheme='Bearer',credentials=token))
    try:
        async with SessionLocal() as db:
            user=await identity(db);await invitations._load(db,user,offer_id)
        await chat_hub.connect(str(offer_id),websocket,str(user.id))
        await websocket.send_json({'type':'ready'})
        while True:
            try: raw=await asyncio.wait_for(websocket.receive_text(),timeout=30)
            except asyncio.TimeoutError:
                async with SessionLocal() as db:
                    await identity(db);await invitations._load(db,user,offer_id)
                continue
            value={}
            try:
                if len(raw)>16000: raise ValueError('Слишком большой запрос')
                value=json.loads(raw)
                if not isinstance(value,dict) or value.get('type')!='message': raise ValueError('Неверный формат')
                body=MessageIn.model_validate(value)
                async with SessionLocal() as db:
                    user=await identity(db);inv,_=await invitations._load(db,user,offer_id)
                    m=await persist_message(db,inv,user,body)
                    packet={'type':'message','message':message_view(m,user),'client_message_id':m.client_message_id}
                await chat_hub.publish(str(offer_id),packet)
            except (ValueError,TypeError):
                await websocket.send_json({'type':'error','message':'Проверьте формат сообщения',
                    'client_message_id':value.get('client_message_id') if isinstance(value,dict) else None})
            except (HTTPException, DomainError) as error:
                if error.status_code==401: raise
                await websocket.send_json({'type':'error','message':error.detail,'client_message_id':value.get('client_message_id')})
    except (HTTPException, DomainError) as error: await websocket.close(code=4401 if error.status_code==401 else 4403)
    except WebSocketDisconnect: pass
    finally: chat_hub.disconnect(str(offer_id),websocket)



@router.post('/api/internal/ats-ai/v1/chat/completions')
async def ats_gigachat_completion(body:dict,request:Request):
    import hmac
    from app.core.config import settings
    expected=settings.ats_service_token.get_secret_value()
    supplied=request.headers.get('authorization','').removeprefix('Bearer ')
    if not expected or not hmac.compare_digest(supplied,expected):raise HTTPException(401,'Service authentication required')
    from app.tasks.rag.llm import get_llm
    from app.tasks.rag.gigachat import GigaChatLLM
    client=get_llm()
    if not isinstance(client,GigaChatLLM):raise HTTPException(503,'GigaChat is not configured')
    messages=body.get('messages',[])
    if not messages or len(json.dumps(messages))>150000:raise HTTPException(422,'Invalid messages')
    payload={'model':client.model,'messages':messages,'temperature':0.1,'max_tokens':min(int(body.get('max_tokens') or body.get('max_completion_tokens') or 3000),6000)}
    schema=body.get('response_format',{}).get('json_schema',{}).get('schema')
    if schema:
        instruction='Return only valid JSON matching this schema: '+json.dumps(schema,ensure_ascii=False)
        system='\n'.join(str(m.get('content','')) for m in messages if m.get('role')=='system')
        payload['messages']=[{'role':'system','content':system+'\n'+instruction},*[m for m in messages if m.get('role')!='system']]
    return await client.request('/chat/completions',payload)
