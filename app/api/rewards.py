from fastapi import APIRouter, Depends
from app.core.deps import get_db
from app.api.endpoint import candidate_only
from app.api.v1._common import candidate_profile
from app.services.reward_service import progress
from app.services.strength_service import recompute_strength, fsp_inputs
from app.domain.ranking import fsp_score
from app.domain.grade_policy import freshness_multiplier, STALE_FLOOR
from datetime import datetime, timezone

router=APIRouter(prefix='/api/rewards',tags=['Rewards'])

@router.get('')
async def rewards(user=Depends(candidate_only),db=Depends(get_db)):
    c=await candidate_profile(db,user.id)
    score=await recompute_strength(db,c)
    achievements=await fsp_inputs(db,c.id)
    freshness=freshness_multiplier(datetime.now(timezone.utc),c.grade_valid_until) if c.confirmed_grade_id else STALE_FLOOR
    data=await progress(db,user.id)
    await db.commit()
    return {**data,'profile_rating':score,'fsp_count':len(achievements),'fsp_rating_bonus':round(25*fsp_score(achievements)*freshness,2),
            'rating_components':{'qualification':round(60*(c.last_test_ratio or 0)*freshness,2),
                                 'fsp':round(25*fsp_score(achievements)*freshness,2),
                                 'tasks':round(15*(c.task_ratio or 0)*freshness,2)}}
