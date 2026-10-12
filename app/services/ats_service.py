"""Private Reqcore bridge. Reports belong to employers; decisions stay human."""
import asyncio
import hashlib
import html
import json
import logging
import re
import base64
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
import httpx
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.candidate import CandidateProfile, CandidateSkill
from app.models.endpoint import EndpointState
from app.models.employer import EmployerProfile
from app.models.reference import Grade, Skill
from app.models.user import User
from app.models.vacancy import Application, Vacancy

log = logging.getLogger('ats.bridge')
_locks = {}


async def request(path, payload):
    async with httpx.AsyncClient(timeout=330) as client:
        response = await client.post(settings.ats_service_url.rstrip('/') + path, json=payload,
                                     headers={'X-Service-Token': settings.ats_service_token.get_secret_value()})
        response.raise_for_status()
        return response.json()


async def read_state(db, user_id, key):
    row = await db.get(EndpointState, (user_id, key))
    return row.data if row else None


async def put_state(db, user_id, key, data):
    row = await db.get(EndpointState, (user_id, key))
    if row:
        row.data = data
    else:
        db.add(EndpointState(user_id=user_id, key=key, data=data))


async def vacancy_context(db, vacancy, ep):
    extra = await read_state(db, ep.user_id, 'vacancy:' + str(vacancy.id)) or {}
    grade = await db.get(Grade, vacancy.grade_id) if vacancy.grade_id else None
    return {'title': vacancy.title, 'description': vacancy.description, 'skills': vacancy.skills or [],
            'salary_max': vacancy.salary_max, 'work_format': vacancy.work_format.value if vacancy.work_format else None,
            'grade': grade.code if grade else extra.get('grade', ''),
            'experience': extra.get('experience', ''), 'requirements': extra.get('requirements', '')}


async def get_settings(db, vacancy, ep):
    context = await vacancy_context(db, vacancy, ep)
    stored = await read_state(db, ep.user_id, 'ats:vacancy:' + str(vacancy.id))
    if stored and stored.get('mode') == 'manual':
        criteria = stored
    else:
        criteria = await request('/auto-config', context)
        if stored and stored.get('reqcore_criteria'):
            criteria['reqcore_criteria'] = stored['reqcore_criteria']
    return {'criteria': criteria, 'vacancy': context, 'mode': criteria['mode']}


async def configuration_signature(db, vacancy, ep):
    source = {'engine': 'reqcore-local-percent-v3', 'vacancy': await vacancy_context(db, vacancy, ep),
              'settings': await read_state(db, ep.user_id, 'ats:vacancy:' + str(vacancy.id))}
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def experience_range(label):
    """Ranges stay ranges; an absent mention is not zero years."""
    if not label:
        return None, None
    value = str(label).strip().lower()
    if value in ('без опыта', 'нет опыта', 'no experience'):
        return 0, 0
    if 'менее' in value or 'less than' in value:
        match = re.search(r'\d+(?:[.,]\d+)?', value)
        return (0, float(match[0].replace(',', '.'))) if match else (None, None)
    numbers = [float(n.replace(',', '.')) for n in re.findall(r'\d+(?:[.,]\d+)?', value)]
    if not numbers:
        return None, None
    if len(numbers) >= 2 and re.search(r'[-–—]|до', value):
        return min(numbers[:2]), max(numbers[:2])
    if 'от' in value or '+' in value or 'более' in value:
        return numbers[0], None
    return numbers[0], numbers[0]


async def candidate_context(db, candidate):
    extra = await read_state(db, candidate.user_id, 'profile') or {}
    skills = (await db.execute(select(Skill.name).join(CandidateSkill, CandidateSkill.skill_id == Skill.id)
                               .where(CandidateSkill.candidate_id == candidate.id))).scalars().all()
    grade = await db.get(Grade, candidate.confirmed_grade_id or candidate.declared_grade_id) if (candidate.confirmed_grade_id or candidate.declared_grade_id) else None
    verified = bool(candidate.confirmed_grade_id and candidate.grade_valid_until and
                    candidate.grade_valid_until > datetime.now(timezone.utc))
    minimum, maximum = experience_range(extra.get('experience'))
    formats = {'Удалённо': ['remote'], 'В офисе': ['office'], 'Гибрид': ['hybrid'],
               'Любой': ['remote', 'office', 'hybrid'], 'Любой формат': ['remote', 'office', 'hybrid']}.get(extra.get('format'), [])
    salary = extra.get('salary')
    number = re.search(r'\d[\d\s\u00a0]*', str(salary)) if salary else None
    salary_min = int(re.sub(r'\s', '', number[0])) if number else None
    resume_text = None
    if extra.get('resume_file_id'):
        file = await read_state(db, candidate.user_id, 'file:' + str(extra['resume_file_id']))
        if file:
            uploads = Path(os.getenv('UPLOAD_DIR', '/app/uploads')).resolve()
            path = (uploads / file.get('storage_key', '')).resolve()
            if path.is_relative_to(uploads) and path.is_file() and path.stat().st_size <= 10_000_000:
                try:
                    parsed = await request('/parse', {'content': base64.b64encode(path.read_bytes()).decode(), 'mime': file.get('mime', '')})
                    resume_text = parsed['text']
                except Exception:
                    log.warning('Resume parsing unavailable for candidate %s', candidate.id)
    return {'grade': grade.code if grade else None, 'grade_verified': verified,
            'experience_min': minimum, 'experience_max': maximum,
            'experience_evidence': ('Заявлено в профиле: ' + str(extra['experience'])) if extra.get('experience') else None,
            'skills': list(skills), 'work_formats': formats, 'salary_min': salary_min,
            'work_experience': extra.get('work_experience', []), 'about': extra.get('about', ''),
            'resume_text': resume_text, 'resume_available': bool(extra.get('resume_file_id'))}


async def evaluate_application(application_id):
    application_id = UUID(str(application_id))
    lock = _locks.setdefault(str(application_id), asyncio.Lock())
    try:
        async with lock:
            async with SessionLocal() as db:
                application = await db.get(Application, application_id)
                if not application:
                    return
                vacancy = await db.get(Vacancy, application.vacancy_id)
                ep = await db.get(EmployerProfile, vacancy.employer_id)
                candidate = await db.get(CandidateProfile, application.candidate_id)
                key = 'ats:application:' + str(application.id)
                try:
                    signature = await configuration_signature(db, vacancy, ep)
                    config = await get_settings(db, vacancy, ep)
                    snapshot = await candidate_context(db, candidate)
                    report = await request('/evaluate', {'candidate': snapshot, 'criteria': config['criteria'],
                                                         'vacancy': config['vacancy'], 'cover_letter': application.cover_letter})
                    report.update(state='ready', vacancy_title=vacancy.title, candidate_name=' '.join(filter(None, [candidate.first_name, candidate.last_name])) or 'Соискатель',
                                  application_id=str(application.id), settings_snapshot=config['criteria'], candidate_snapshot=snapshot,
                                  configuration_signature=signature)
                    await db.refresh(vacancy)
                    row = await db.get(EndpointState, (ep.user_id, 'ats:vacancy:' + str(vacancy.id)))
                    if row: await db.refresh(row)
                    if signature != await configuration_signature(db, vacancy, ep):
                        report = {'state': 'pending', 'category': 'review', 'summary': 'Требования изменились. Ожидается новая оценка.'}
                    await put_state(db, ep.user_id, key, report)
                except Exception:
                    log.exception('ATS evaluation failed for application %s', application.id)
                    await put_state(db, ep.user_id, key, {'state': 'error', 'category': 'review',
                                    'summary': 'Оценка временно недоступна. Отклик доступен для ручного рассмотрения.'})
                await db.commit()
    finally:
        if not lock.locked() and not getattr(lock, '_waiters', None):
            _locks.pop(str(application_id), None)


async def evaluate_many(ids):
    for application_id in ids:
        await evaluate_application(application_id)


async def retry_pending(db):
    """Run after restart and retry service outages without modifying human decisions."""
    rows = (await db.execute(select(EndpointState).where(EndpointState.key.like('ats:application:%')))).scalars().all()
    for row in rows:
        app_id = row.key.rsplit(':', 1)[1]
        if row.data.get('state') in ('pending', 'error'):
            await evaluate_application(app_id)


def export_html(report):
    esc = lambda value: html.escape(str(value if value is not None else '—'))
    rows = ''.join('<tr><td>' + esc(r['label']) + '</td><td>' + esc(r['requirement']) + '</td><td>' + esc(r['evidence']) + '<p>Сильные стороны: ' + esc('; '.join(r.get('strengths', []))) + '</p><p>Пробелы: ' + esc('; '.join(r.get('gaps', []))) + '</p></td><td>' + esc({'match': 'Совпадает', 'mismatch': 'Расхождение', 'unknown': 'Уточнить'}.get(r['status'], r['status'])) + '</td></tr>' for r in report.get('criteria', []))
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Отчёт по отклику</title>'
            '<style>body{font:16px/1.6 Arial;max-width:1000px;margin:40px auto;padding:24px;color:#222}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:10px;text-align:left}button{padding:10px}@media print{button{display:none}}</style>'
            '<h1>Отчёт по отклику</h1><p>' + esc(report.get('candidate_name')) + ' · ' + esc(report.get('vacancy_title')) + '</p><p>' + esc(report.get('summary')) + '</p><p>Оценка: ' + esc(report.get('score')) + ' из 100. Покрытие данных: ' + esc(report.get('coverage')) + '%.</p>'
            '<table><tr><th>Критерий</th><th>Требование</th><th>Основание</th><th>Результат</th></tr>' + rows + '</table><p>' + esc(report.get('notice')) + '</p><button onclick="window.print()">Печать или сохранить в PDF</button></html>')
