"""Immutable assignment versions and exact vacancy linkage, stored without schema changes."""
from copy import deepcopy
from sqlalchemy import select
from app.models.endpoint import EndpointState
from app.models.employer import EmployerProfile
from app.models.candidate import CandidateProfile

async def freeze_task(db,task,metadata=None):
    ep=await db.get(EmployerProfile,task.employer_id)
    rows=(await db.execute(select(EndpointState).where(EndpointState.user_id==ep.user_id,EndpointState.key.like('taskset:%')))).scalars().all()
    matches=[(row.key.split(':',1)[1],item) for row in rows for item in row.data.get('tasks',[]) if item.get('task_id')==str(task.id)]
    metadata=deepcopy(metadata if metadata is not None else (matches[0][1] if len(matches)==1 else {}))
    vacancy_id=metadata.get('vacancy_id') or (matches[0][0] if len(matches)==1 else None)
    from app.models.vacancy import Vacancy
    from uuid import UUID
    vacancy=await db.get(Vacancy,UUID(vacancy_id)) if vacancy_id else None
    return {**metadata,'task_id':str(task.id),'title':metadata.get('title',task.title),'condition':metadata.get('condition',task.statement),
        'language':task.language,'rubric':deepcopy(task.rubric or []),'vacancy_id':vacancy_id,'vacancy_title':metadata.get('vacancy_title') or (vacancy.title if vacancy else None),'version':1}

async def assignment_version(db,assignment,task):
    c=await db.get(CandidateProfile,assignment.candidate_id)
    key='assignment:version:'+str(assignment.id)
    row=await db.get(EndpointState,(c.user_id,key))
    if row:return deepcopy(row.data)
    from app.models.invitation import Invitation
    ep=await db.get(EmployerProfile,task.employer_id)
    invitations=(await db.execute(select(Invitation).where(Invitation.candidate_id==c.id,Invitation.employer_id==ep.id))).scalars().all()
    matches=[]
    for invitation in invitations:
        sent=await db.get(EndpointState,(ep.user_id,'assessment-invitation:'+str(invitation.id)))
        for item in (sent.data.get('tasks',[]) if sent else []):
            if item.get('task_id')==str(task.id):
                matches.append({**deepcopy(item),'offer_id':str(invitation.id),'vacancy_id':str(invitation.vacancy_id) if invitation.vacancy_id else None})
    value={**await freeze_task(db,task,matches[0]),**matches[0]} if len(matches)==1 else await freeze_task(db,task)
    db.add(EndpointState(user_id=c.user_id,key=key,data=value))
    await db.flush()
    return value

async def freeze_assignment(db,assignment,candidate_user_id,version):
    key='assignment:version:'+str(assignment.id)
    row=await db.get(EndpointState,(candidate_user_id,key))
    if not row:db.add(EndpointState(user_id=candidate_user_id,key=key,data=deepcopy(version)))
    await db.flush()

def evaluation_status(assignment):
    if assignment.status=='expired':return 'expired'
    if assignment.status=='evaluating':return 'checking'
    if assignment.reviewer_score is not None:return 'passed' if assignment.reviewer_score>=.7 else 'failed'
    if (assignment.eval_details or {}).get('error'):return 'unavailable'
    if assignment.auto_score is not None and assignment.auto_score<.7:return 'failed'
    return 'awaiting_employer' if assignment.status in ('submitted','reviewed') else 'assigned'
