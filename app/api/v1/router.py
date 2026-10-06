from fastapi import APIRouter

from app.api.v1 import assessments, auth, candidates, employers, invitations, ref, search, vacancies

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(candidates.router)
api_router.include_router(assessments.router)
api_router.include_router(employers.router)
api_router.include_router(invitations.router)
api_router.include_router(ref.router)
api_router.include_router(search.router)
api_router.include_router(vacancies.router)
