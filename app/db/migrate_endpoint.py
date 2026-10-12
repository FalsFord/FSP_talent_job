"""One-time, transactional migration from the former EndPoint schema.

Usage: python -m app.db.migrate_endpoint /tmp/endpoint-legacy.json
The old database and file volume are never removed by this script.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select, text, func
from app.db.session import SessionLocal
from app.models import *  # noqa: F403: load all model metadata
from app.models.user import User, UserRole
from app.models.candidate import CandidateProfile, CandidateSkill, SkillStatus
from app.models.reference import Skill
from app.models.employer import EmployerProfile, Company, WorkFormat
from app.models.vacancy import Vacancy
from app.models.invitation import Invitation, InvitationStatus
from app.models.platform import EmployerTask, TaskAssignment, ContactReveal
from app.models.endpoint import EndpointState, ChatMessage
from app.services.profile_service import refresh_candidate_search_index

def uid(table, value):
    return uuid5(NAMESPACE_URL, f'endpoint-legacy:{table}:{value}')

def number(value):
    try: return int(str(value).replace(' ', '').replace('\u00a0', ''))
    except (ValueError, TypeError): return 0

def date(value):
    return datetime.fromisoformat(value) if value else datetime.now(timezone.utc)

async def migrate(filename):
    legacy = json.loads(Path(filename).read_text(encoding='utf8'))
    users, candidates, employers, vacancies = {}, {}, {}, {}
    async with SessionLocal() as db:
        marker = await db.scalar(select(EndpointState).where(EndpointState.key == 'legacy:migration-complete').limit(1))
        if marker:
            print('Legacy migration already completed; no data changed.')
            return
        async def put(user_id, key, data):
            row = await db.get(EndpointState, (user_id, key))
            if row: row.data = data
            else: db.add(EndpointState(user_id=user_id, key=key, data=data))

        # Reuse a seeded identity with the same email, keeping the user's old password.
        for row in legacy['users']:
            user = await db.scalar(select(User).where(User.email == row['email'].lower()))
            if not user:
                user = User(id=uid('users', row['id']), email=row['email'].lower(), role=UserRole(row['role']))
                db.add(user)
            if user.role.value != row['role']:
                raise ValueError('Migration stopped: duplicate email with another role')
            user.password_hash = row['password_hash']
            user.is_active = row['active']
            user.email_verified = True
            user.created_at = date(row['created_at'])
            users[row['id']] = user.id
        await db.flush()
        for row in legacy.get('candidate_profiles', []):
            user_id = users[row['user_id']]
            data = row['data']
            profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
            if not profile:
                profile = CandidateProfile(id=uid('candidates', row['user_id']), user_id=user_id)
                db.add(profile)
            candidates[row['user_id']] = profile.id
            profile.first_name, profile.last_name = data.get('name', ''), data.get('surname', '')
            profile.headline, profile.city = data.get('role'), data.get('city')
            profile.phone, profile.about = data.get('phone'), data.get('about')
            profile.remote_ok = data.get('format') != 'В офисе'
            profile.onboarding_completed = bool(data.get('complete'))
            profile.is_discoverable = True
            profile.privacy = {'show_contacts_after_accept': True, 'show_full_name': False}
            extension = {k:v for k,v in data.items() if k not in ('id', 'grade', 'photo', 'resume', 'resume_url', 'resume_file_id', 'avatar_file_id')}
            for kind in ('resume', 'avatar'):
                if row.get(kind + '_file_id'):
                    extension[kind + '_file_id'] = str(uid('files', row[kind + '_file_id']))
            await put(user_id, 'profile', extension)
            await db.flush()
            for name in data.get('tech', []):
                skill = await db.scalar(select(Skill).where(func.lower(Skill.name) == name.lower()))
                if not skill:
                    skill = Skill(name=name, slug='legacy-' + uid('skill',name.lower()).hex); db.add(skill); await db.flush()
                exists = await db.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == profile.id, CandidateSkill.skill_id == skill.id))
                if not exists: db.add(CandidateSkill(candidate_id=profile.id, skill_id=skill.id, status=SkillStatus.claimed))
            await db.flush()
            await refresh_candidate_search_index(db, profile)
        for row in legacy.get('employer_profiles', []):
            user_id, data = users[row['user_id']], row['data']
            profile = await db.scalar(select(EmployerProfile).where(EmployerProfile.user_id == user_id))
            if not profile:
                company = Company(id=uid('companies', row['user_id']), name=data.get('company') or 'Компания')
                db.add(company); await db.flush()
                profile = EmployerProfile(id=uid('employers', row['user_id']), user_id=user_id, company_id=company.id)
                db.add(profile)
            else: company = await db.get(Company, profile.company_id)
            company.name = data.get('company') or company.name
            company.description, company.website, company.industry = data.get('description'), data.get('website'), data.get('sector')
            profile.position = data.get('position')
            employers[row['user_id']] = profile.id
            await put(user_id, 'company', {k:v for k,v in data.items() if k in ('representative','position','size')})
            if row.get('active_vacancy_id'):
                await put(user_id, 'settings', {'active_vacancy_id': str(uid('vacancies', row['active_vacancy_id']))})
        await db.flush()
        for row in legacy.get('vacancies', []):
            data = row['data']; key = uid('vacancies', row['id']); vacancies[row['id']] = key
            vacancy = Vacancy(id=key, employer_id=employers[row['employer_id']], title=data.get('title') or 'Вакансия',
                description=data.get('tasks') or data.get('requirements') or data.get('description') or '',
                skills=data.get('tech') or [], salary_min=number(data.get('salaryMin')), salary_max=number(data.get('salaryMax')),
                work_format=WorkFormat.office if data.get('format') == 'В офисе' else WorkFormat.hybrid if data.get('format') == 'Гибрид' else WorkFormat.remote,
                is_active=row['published'], created_at=date(row['created_at']))
            db.add(vacancy)
            await put(users[row['employer_id']], 'vacancy:' + str(key), {k:v for k,v in data.items() if k != 'id'})
        await db.flush()
        vacancy_owners = {r['id']: r['employer_id'] for r in legacy.get('vacancies', [])}
        for row in legacy.get('task_sets', []):
            owner = vacancy_owners[row['vacancy_id']]; saved = []
            for index, task in enumerate(row['tasks']):
                task_id = uid('tasks', str(row['vacancy_id']) + ':' + str(index))
                db.add(EmployerTask(id=task_id, employer_id=employers[owner], title=task.get('title') or 'Задание',
                    statement=task.get('condition') or '', language='python', origin='manual', rubric=[], sources=[]))
                saved.append({**task, 'task_id':str(task_id)})
            await put(users[owner], 'taskset:' + str(vacancies[row['vacancy_id']]), {'tasks':saved})
        await db.flush()
        for row in legacy.get('offers', []):
            vacancy = await db.get(Vacancy, vacancies[row['vacancy_id']])
            status = {'new':'sent','accepted':'accepted','declined':'declined'}[row['status']]
            invitation_id = uid('offers', row['id'])
            inv = Invitation(id=invitation_id, candidate_id=candidates[row['candidate_id']], employer_id=employers[row['employer_id']],
                vacancy_id=vacancy.id, title=vacancy.title, message=vacancy.description or '', salary_min=vacancy.salary_min,
                salary_max=vacancy.salary_max, status=InvitationStatus(status), contact_method=None, created_at=date(row['created_at']))
            db.add(inv)
            if status == 'accepted':
                reveal = await db.scalar(select(ContactReveal).where(ContactReveal.candidate_id == inv.candidate_id, ContactReveal.employer_id == inv.employer_id))
                if not reveal: db.add(ContactReveal(candidate_id=inv.candidate_id, employer_id=inv.employer_id, source='invitation', source_id=invitation_id))
        await db.flush()
        for row in legacy.get('messages', []):
            db.add(ChatMessage(id=row['id'], offer_id=uid('offers', row['offer_id']), sender_id=users[row['sender_id']],
                text=row['text'], client_message_id=row.get('client_message_id'), created_at=date(row['created_at'])))
        for row in legacy.get('uploaded_files', []):
            await put(users[row['owner_id']], 'file:' + str(uid('files', row['id'])),
                {'name':row['original_name'], 'kind':row['kind'], 'mime':row['content_type'], 'storage_key':row['storage_key']})
        for employer in employers:
            ids = [str(candidates[r['candidate_id']]) for r in legacy.get('favorites', []) if r['employer_id'] == employer]
            await put(users[employer], 'favorites', {'ids':ids})
        for row in legacy.get('editor_drafts', []):
            key = row['key']
            for offer in legacy.get('offers', []):
                key = key.replace(f"endpoint-assignment-code-{offer['id']}-", f"endpoint-assignment-code-{uid('offers',offer['id'])}-")
            await put(users[row['user_id']], 'draft:' + key, row['data'])
        for row in legacy.get('assessments', []):
            data = row['state']
            await put(users[row['user_id']], 'legacy:assessment:' + row['kind'], data)
            # An unfinished old test cannot be submitted as a native FSP session.
            if row['kind'] == 'grade' and data.get('done'):
                await put(users[row['user_id']], 'assessment:grade', {**data, 'legacy':True})
            if row['kind'] == 'assignment' and data.get('offerId'):
                await put(users[row['user_id']], 'assessment:assignment', {**data, 'offerId':str(uid('offers', data['offerId']))})
        for row in legacy.get('code_submissions', []):
            await put(users[row['user_id']], 'submission:' + row['token'], {'created_at':row['created_at']})
        await db.flush()
        await db.execute(text("SELECT setval(pg_get_serial_sequence('endpoint_chat_messages','id'), COALESCE((SELECT MAX(id) FROM endpoint_chat_messages),1), EXISTS(SELECT 1 FROM endpoint_chat_messages))"))
        await put(next(iter(users.values())), 'legacy:migration-complete', {'counts':{k:len(v) for k,v in legacy.items()}, 'migrated_at':datetime.now(timezone.utc).isoformat()})
        await db.commit()
        print('Migration committed:', {k:len(v) for k,v in legacy.items() if k in ('users','candidate_profiles','employer_profiles','vacancies','offers','messages','uploaded_files')})

if __name__ == '__main__':
    asyncio.run(migrate(sys.argv[1]))
