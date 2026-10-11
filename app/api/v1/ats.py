from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import select
from app.api.v1._common import employer_profile
from app.api.v1.vacancies import _own_vacancy
from app.core.deps import get_db, require_roles
from app.models.user import UserRole
from app.models.vacancy import Application, Vacancy
from app.services import ats_service as ats

router = APIRouter(prefix='/vacancies', tags=['ats'])
employer_only = require_roles(UserRole.employer)


@router.get('/{vacancy_id}/ats/settings')
async def settings(vacancy_id: UUID, user=Depends(employer_only), db=Depends(get_db)):
    ep = await employer_profile(db, user.id)
    vacancy = await _own_vacancy(db, ep, vacancy_id)
    try:
        return await ats.get_settings(db, vacancy, ep)
    except Exception:
        raise HTTPException(503, 'Сервис оценки временно недоступен')


@router.put('/{vacancy_id}/ats/settings')
async def save_settings(vacancy_id: UUID, body: dict, tasks: BackgroundTasks, user=Depends(employer_only), db=Depends(get_db)):
    ep = await employer_profile(db, user.id)
    vacancy = await _own_vacancy(db, ep, vacancy_id)
    try:
        criteria = await ats.request('/validate-config', body)
    except Exception as error:
        import httpx
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 422:
            raise HTTPException(422, 'Проверьте критерии: грейд, веса и пороги оценки')
        raise HTTPException(503, 'Сервис оценки временно недоступен')
    await ats.put_state(db, ep.user_id, 'ats:vacancy:' + str(vacancy.id), criteria)
    ids = (await db.execute(select(Application.id).where(Application.vacancy_id == vacancy.id))).scalars().all()
    for app_id in ids:
        await ats.put_state(db, ep.user_id, 'ats:application:' + str(app_id), {'state': 'pending', 'category': 'review', 'summary': 'Пересчёт по новым требованиям'})
    await db.commit()
    tasks.add_task(ats.evaluate_many, ids)
    return await ats.get_settings(db, vacancy, ep)


@router.post('/{vacancy_id}/ats/recalculate')
async def recalculate(vacancy_id: UUID, tasks: BackgroundTasks, user=Depends(employer_only), db=Depends(get_db)):
    ep = await employer_profile(db, user.id)
    await _own_vacancy(db, ep, vacancy_id)
    ids = (await db.execute(select(Application.id).where(Application.vacancy_id == vacancy_id))).scalars().all()
    for app_id in ids:
        await ats.put_state(db, ep.user_id, 'ats:application:' + str(app_id), {'state': 'pending', 'category': 'review', 'summary': 'Оценка выполняется'})
    await db.commit()
    tasks.add_task(ats.evaluate_many, ids)
    return {'queued': len(ids)}


@router.post('/{vacancy_id}/ats/generate')
async def generate_settings(vacancy_id: UUID, user=Depends(employer_only), db=Depends(get_db)):
    ep = await employer_profile(db, user.id)
    vacancy = await _own_vacancy(db, ep, vacancy_id)
    try:
        criteria = await ats.request('/generate-config', await ats.vacancy_context(db, vacancy, ep))
    except Exception:
        raise HTTPException(503, 'Reqcore не смог сформировать критерии. Проверьте локальную модель.')
    # Preview only: the employer reviews and saves generated criteria explicitly.
    return {'criteria': criteria}


@router.get('/applications/{application_id}/ats/report')
async def report(application_id: UUID, download: bool = False, user=Depends(employer_only), db=Depends(get_db)):
    ep = await employer_profile(db, user.id)
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(404, 'Отклик не найден')
    await _own_vacancy(db, ep, application.vacancy_id)
    value = await ats.read_state(db, ep.user_id, 'ats:application:' + str(application_id))
    if not value or value.get('state') != 'ready':
        raise HTTPException(409, 'Отчёт ещё не готов')
    if download:
        return Response(ats.export_html(value), media_type='text/html', headers={
            'Content-Disposition': 'attachment; filename="application-report-' + str(application_id) + '.html"'})
    return value
