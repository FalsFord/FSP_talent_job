"""Invitation quotas and pair cooldown must not block employer invitations."""
import test_git_rewards as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerProfile
from app.models.vacancy import Vacancy, Application
from app.services.invitation_service import create_invitation


def verify():
    with TestClient(app) as client:
        async def run():
            async with SessionLocal() as db:
                employer = await db.scalar(select(EmployerProfile).join(User).where(User.email == 'employer@demo.local'))
                user = await db.get(User, employer.user_id)
                candidate = await db.scalar(select(CandidateProfile).join(User).where(User.email == 'candidate@demo.local'))
                vacancy = Vacancy(employer_id=employer.id, title='Unlimited invitations', description='Fixture', salary_min=1, salary_max=2, is_active=True)
                db.add(vacancy)
                await db.flush()
                db.add(Application(candidate_id=candidate.id, vacancy_id=vacancy.id))
                await db.flush()
                data = dict(candidate_id=candidate.id, vacancy_id=vacancy.id, title='Join our team', message='Invitation fixture', salary_min=1, salary_max=2)
                ids = set()
                for index in range(25):
                    invitation = await create_invitation(db, employer, user, data, str(index))
                    ids.add(invitation.id)
                assert len(ids) == 25
                repeated = await create_invitation(db, employer, user, data, '24')
                assert repeated.id == invitation.id
                await db.commit()
        client.portal.call(run)
    print('PASS 25 immediate invitations to one candidate, idempotent request preserved')


if __name__ == '__main__':
    base.asyncio.run(base.database(True))
    try:
        base.subprocess.run([base.sys.executable, '-m', 'app.db.init_db'], check=True)
        base.subprocess.run([base.sys.executable, '-m', 'app.db.seed'], check=True)
        verify()
    finally:
        base.asyncio.run(base.database(False))
