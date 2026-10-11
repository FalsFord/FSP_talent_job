"""Registration readiness is independent of a candidate's confirmed grade."""
from sqlalchemy import select

from app.core.errors import DomainError
from app.models.assessment import AssessmentSession, SessionStatus
from app.models.candidate import CandidateSkill
from app.models.endpoint import EndpointState


async def registration_issues(db, profile):
    row = await db.get(EndpointState, (profile.user_id, 'profile'))
    extra = row.data if row else {}
    issues = []
    fields = [('first_name', 'Укажите имя'), ('last_name', 'Укажите фамилию'),
              ('phone', 'Укажите телефон'), ('city', 'Укажите город'),
              ('headline', 'Выберите желаемую роль')]
    for field, label in fields:
        if not str(getattr(profile, field) or '').strip():
            issues.append({'message': label, 'url': '/candidate/about' if field != 'headline' else '/candidate/preferences'})
    skill = await db.scalar(select(CandidateSkill.id).where(CandidateSkill.candidate_id == profile.id).limit(1))
    if not skill:
        issues.append({'message': 'Добавьте хотя бы одну технологию', 'url': '/candidate/preferences'})
    if not extra.get('consent'):
        issues.append({'message': 'Подтвердите согласие на обработку данных в анкете', 'url': '/candidate/about'})
    submitted = await db.scalar(select(AssessmentSession.id).where(
        AssessmentSession.candidate_id == profile.id, AssessmentSession.purpose == 'onboarding',
        AssessmentSession.status == SessionStatus.submitted, AssessmentSession.submitted_at.is_not(None)).limit(1))
    if not submitted:
        issues.append({'message': 'Завершите вводный тест и отправьте ответы', 'url': '/candidate/test'})
    return issues


async def registration_status(db, profile):
    if profile.onboarding_completed:
        return {'complete': True, 'can_complete': False, 'issues': []}
    issues = await registration_issues(db, profile)
    return {'complete': False, 'can_complete': not issues, 'issues': issues}


async def complete_registration(db, profile):
    if profile.onboarding_completed:
        return
    issues = await registration_issues(db, profile)
    if issues:
        raise DomainError('REGISTRATION_INCOMPLETE',
                          'Регистрация не завершена: ' + '; '.join(i['message'] for i in issues) + '.',
                          409, errors=issues)
    profile.onboarding_completed = True
    await db.flush()


async def require_completed_registration(db, profile):
    status = await registration_status(db, profile)
    if not status['complete']:
        reasons = '; '.join(i['message'] for i in status['issues']) or 'Подтвердите завершение регистрации в профиле'
        raise DomainError('REGISTRATION_INCOMPLETE',
                          'Чтобы откликнуться, завершите регистрацию: ' + reasons + '.',
                          409, errors=status['issues'])
