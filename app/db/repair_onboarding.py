"""Repair profiles that completed the UI flow but failed the introductory grade test."""
import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.candidate import CandidateProfile
from app.models.endpoint import EndpointState
from app.services.onboarding_service import registration_issues


async def main():
    repaired = 0
    async with SessionLocal() as db:
        profiles = (await db.execute(select(CandidateProfile).where(CandidateProfile.onboarding_completed == False))).scalars().all()
        for profile in profiles:
            row = await db.get(EndpointState, (profile.user_id, 'profile'))
            if row and row.data.get('complete') is True and not await registration_issues(db, profile):
                profile.onboarding_completed = True
                repaired += 1
        await db.commit()
    print(f'Completed registration flags repaired: {repaired}')


if __name__ == '__main__':
    asyncio.run(main())
