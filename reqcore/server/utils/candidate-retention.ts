import { and, eq, isNotNull, isNull } from 'drizzle-orm'
import { candidate } from '../database/schema'
import { recordRetentionAudit } from './erasure'

/**
 * Return a candidate only when it belongs to the organization and is not in
 * retention quarantine. Use this for operations that would add or mutate data.
 */
export async function findActiveCandidate(orgId: string, candidateId: string) {
  return db.query.candidate.findFirst({
    where: and(
      eq(candidate.id, candidateId),
      eq(candidate.organizationId, orgId),
      isNull(candidate.quarantinedAt),
    ),
    columns: { id: true },
  })
}

/**
 * A new public application is fresh engagement by the data subject. Restore a
 * matching quarantined candidate and reset the retention clock before attaching
 * the new application. This is intentionally idempotent.
 */
export async function restoreCandidateForPublicApplication(
  orgId: string,
  candidateId: string,
): Promise<boolean> {
  const now = new Date()
  const [restored] = await db.update(candidate)
    .set({
      quarantinedAt: null,
      scheduledPurgeAt: null,
      retentionReviewedAt: now,
      updatedAt: now,
    })
    .where(and(
      eq(candidate.id, candidateId),
      eq(candidate.organizationId, orgId),
      isNotNull(candidate.quarantinedAt),
    ))
    .returning({ id: candidate.id })

  if (!restored) return false

  await recordRetentionAudit(orgId, candidateId, 'restored', 'success', null, {
    source: 'public_application',
  })
  logInfo('retention.candidate_restored_on_application', {
    org_id: orgId,
    candidate_id: candidateId,
  })
  return true
}
