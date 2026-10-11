import { eq, and, isNull } from 'drizzle-orm'
import { candidate, orgSettings } from '../../database/schema'
import { candidateIdParamSchema } from '../../utils/schemas/candidate'
import { eraseCandidates, recordRetentionAudit } from '../../utils/erasure'
import type { H3Event } from 'h3'

/**
 * DELETE /api/candidates/:id
 *
 * Two modes, so an everyday click can never irreversibly destroy data:
 *
 *  - Default (SOFT delete): the candidate is quarantined — hidden from lists but
 *    fully recoverable from Settings → Privacy & Retention. Nothing is erased.
 *    This is what the recruiter "Delete" button does.
 *
 *  - ?permanent=true (HARD erase): permanent GDPR erasure — DB graph + S3 objects
 *    + polymorphic rows, via the shared erasure path. Irreversible. Only the
 *    retention review screen triggers this, behind a type-the-name confirmation.
 * Both modes are blocked for candidates on an active legal hold. Permanent
 * erasure can be explicitly forced with ?override=true for exceptional cases.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['delete'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, candidateIdParamSchema.parse)
  const query = getQuery(event)
  const permanent = query.permanent === 'true'
  const override = permanent && query.override === 'true'

  // A legal hold prevents both quarantine and permanent erasure. The explicit
  // override is intentionally limited to permanent erasure so an ordinary
  // recruiter delete can never sidestep the hold.
  const existing = await db.query.candidate.findFirst({
    where: and(eq(candidate.id, id), eq(candidate.organizationId, orgId)),
    columns: { retentionExemptUntil: true },
  })
  if (existing?.retentionExemptUntil && existing.retentionExemptUntil > new Date() && !override) {
    throw createError({
      statusCode: 409,
      statusMessage: 'Candidate is under a legal hold and cannot be deleted',
    })
  }

  if (!permanent) {
    return softDeleteCandidate(event, orgId, id, session.user.id)
  }

  const report = await eraseCandidates(orgId, [id], {
    actorId: session.user.id,
    auditMetadata: override ? { legalHoldOverride: 'true' } : undefined,
  })
  const result = report.results[0]

  if (!result || result.status === 'not_found') {
    throw createError({ statusCode: 404, statusMessage: 'Not found' })
  }

  if (result.status === 'skipped_s3_failure') {
    // Storage objects couldn't be removed — refuse to leave a partially-erased
    // record. The candidate is untouched and can be retried.
    throw createError({ statusCode: 502, statusMessage: 'Storage deletion failed; candidate not erased' })
  }
  if (result.auditFailed) {
    logError('retention.manual_erasure_audit_failed', {
      org_id: orgId,
      candidate_id: id,
      actor_id: session.user.id,
    })
  }

  recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'deleted',
    resourceType: 'candidate',
    resourceId: id,
  })

  setResponseStatus(event, 204)
  return null
})

/**
 * Quarantine the candidate instead of erasing it. Recoverable via the restore
 * endpoint / retention review screen. Idempotent: an already-quarantined
 * candidate succeeds without changes.
 */
async function softDeleteCandidate(
  event: H3Event,
  orgId: string,
  id: string,
  actorId: string,
) {
  const existing = await db.query.candidate.findFirst({
    where: and(eq(candidate.id, id), eq(candidate.organizationId, orgId)),
    columns: { id: true, quarantinedAt: true },
  })
  if (!existing) {
    throw createError({ statusCode: 404, statusMessage: 'Not found' })
  }
  if (existing.quarantinedAt) {
    return { id, status: 'quarantined' as const }
  }

  // Mirror the org's configured quarantine window so a manual delete behaves like
  // retention quarantine: recoverable now, and swept by the retention job later
  // (only if the org has automated cleanup enabled — otherwise it stays forever).
  const settings = await db.query.orgSettings.findFirst({
    where: eq(orgSettings.organizationId, orgId),
    columns: { quarantineDays: true },
  })
  const quarantineDays = settings?.quarantineDays ?? 30
  const now = new Date()
  const purgeAt = new Date(now.getTime() + quarantineDays * 24 * 60 * 60 * 1000)

  const [updated] = await db.update(candidate)
    .set({ quarantinedAt: now, scheduledPurgeAt: purgeAt, updatedAt: now })
    .where(and(
      eq(candidate.id, id),
      eq(candidate.organizationId, orgId),
      isNull(candidate.quarantinedAt),
    ))
    .returning({ id: candidate.id })
  // Lost a race to a concurrent quarantine — still the desired end state.
  if (!updated) {
    return { id, status: 'quarantined' as const }
  }

  const audited = await recordRetentionAudit(orgId, id, 'quarantined', 'success', actorId, {
    source: 'manual',
  })
  if (!audited) {
    logError('retention.manual_soft_delete_audit_failed', {
      org_id: orgId,
      candidate_id: id,
      actor_id: actorId,
    })
  }
  recordActivity({
    organizationId: orgId,
    actorId,
    action: 'deleted',
    resourceType: 'candidate',
    resourceId: id,
  })

  return { id, status: 'quarantined' as const }
}
