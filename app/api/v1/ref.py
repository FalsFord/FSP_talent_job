from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.reference import Grade, Specialization

router = APIRouter(prefix="/ref", tags=["reference"])


@router.get("/specializations")
async def list_specializations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Specialization).order_by(Specialization.sort_order))
    return [{"id": s.id, "code": s.code, "name": s.name} for s in result.scalars().all()]


@router.get("/grades")
async def list_grades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Grade).order_by(Grade.sort_order))
    return [{"id": g.id, "code": g.code, "name": g.name, "level": g.level} for g in result.scalars().all()]
