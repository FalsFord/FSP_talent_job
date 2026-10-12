from sqlalchemy import select
from app.models.vacancy import Application, Vacancy
from app.models.invitation import Invitation


async def eligible_candidate_ids(db, employer_id, vacancy_id=None):
    applications = select(Application.candidate_id).join(Vacancy, Vacancy.id == Application.vacancy_id).where(Vacancy.employer_id == employer_id)
    offers = select(Invitation.candidate_id).where(Invitation.employer_id == employer_id)
    if vacancy_id is not None:
        applications = applications.where(Application.vacancy_id == vacancy_id)
        offers = offers.where(Invitation.vacancy_id == vacancy_id)
    return set((await db.execute(applications.union(offers))).scalars().all())
