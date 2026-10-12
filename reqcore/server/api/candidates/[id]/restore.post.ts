/**
 * POST /api/candidates/:id/restore
 *
 * Pull a candidate back out of the quarantine window before permanent erasure.
 * Clears the quarantine markers AND stamps `retentionReviewedAt = now` so the
 * candidate gets a fresh retention window. Without that reset the underlying
 * anchor (latest application activity / creation date) is unchanged, so the very
 * next retention sweep would recompute the candidate as expired and immediately
 * re-quarantine it — making restore a no-op.
 */
import { eq, and, isNotNull } from 'drizzle-orm'
import { candidate } from '../../../database/schema'
import { candidateIdParamSchema } from '../../../utils/schemas/candidate'
import { recordRetentionAudit } from '../../../utils/erasure'

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['delete'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, candidateIdParamSchema.parse)

  const now = new Date()
  const [restored] = await db.update(candidate)
    .set({ quarantinedAt: null, scheduledPurgeAt: null, retentionReviewedAt: now, updatedAt: now })
    .where(and(
      eq(candidate.id, id),
      eq(candidate.organizationId, orgId),
      isNotNull(candidate.quarantinedAt),
    ))
    .returning({ id: candidate.id })

  if (!restored) {
    throw createError({ statusCode: 404, statusMessage: 'Not quarantined or not found' })
  }

  await recordRetentionAudit(orgId, id, 'restored', 'success', session.user.id, {})
  await recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'updated',
    resourceType: 'candidate',
    resourceId: id,
    metadata: { retentionAction: 'restored_from_quarantine' },
  })

  return { id, restored: true }
})
