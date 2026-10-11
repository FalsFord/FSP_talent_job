import asyncio
from uuid import UUID
from app.db.session import SessionLocal
from app.models.vacancy import Vacancy
from app.models.employer import EmployerProfile
from app.models.user import User
from app.core.security import create_access_token
import httpx
async def main():
    async with SessionLocal() as db:
        v=await db.get(Vacancy,UUID('d5a0fc35-b69f-50a7-af13-a48c8d3d4459'))
        ep=await db.get(EmployerProfile,v.employer_id)
        user=await db.get(User,ep.user_id)
        from app.core.security import password_version
        token=create_access_token(str(user.id),extra={'role':user.role.value,'ver':password_version(user)})
    async with httpx.AsyncClient() as client:
        r=await client.get('http://127.0.0.1:8000/api/employer/submissions',headers={'Authorization':'Bearer '+token},timeout=60)
        print('STATUS',r.status_code)
        if r.status_code!=200: print(r.text[:600]);return
        data=r.json();print('CANDIDATES',len(data));print('REPORTS',len(data))
asyncio.run(main())



