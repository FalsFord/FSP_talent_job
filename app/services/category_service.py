import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Category
from app.models.reference import Grade, Specialization


async def ensure_category(db: AsyncSession, specialization_id: uuid.UUID, grade_id: uuid.UUID) -> Category:
    result = await db.execute(
        select(Category).where(
            Category.specialization_id == specialization_id,
            Category.grade_id == grade_id,
        )
    )
    cat = result.scalar_one_or_none()
    if cat:
        return cat
    spec = await db.get(Specialization, specialization_id)
    grade = await db.get(Grade, grade_id)
    slug = f"{spec.code}-{grade.code}"
    label = f"{spec.name} · {grade.name}"
    cat = Category(specialization_id=specialization_id, grade_id=grade_id, slug=slug, label=label)
    db.add(cat)
    await db.flush()
    return cat
