/**
 * GET /api/admin/retention/review
 *
 * Upcoming-deletion review for the active org: candidates that are expiring
 * soon, already expired (awaiting the next sweep), or in the recoverable
 * quarantine window. Drives the retention review UI in settings.
 *
 * Returns candidate PII (name/email) — this is an authenticated in-app admin
 * view, distinct from the privacy-safe `retention_audit` log.
 */
import { eq, and, max } from 'drizzle-orm'
import { candidate, application, orgSettings } from '../../../database/schema'
import { computeRetentionState } from '../../../utils/retention'

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['delete'] })
  const orgId = session.session.activeOrganizationId

  const settings = await db.query.orgSettings.findFirst({
    where: eq(orgSettings.organizationId, orgId),
    columns: { retentionEnabled: true, retentionMonths: true, retentionActivatedAt: true },
  })

  const retentionMonths = settings?.retentionMonths ?? 24
  const retentionActivatedAt = settings?.retentionActivatedAt ?? null

  const candidates = await db.query.candidate.findMany({
    where: eq(candidate.organizationId, orgId),
    columns: {
      id: true, firstName: true, lastName: true, email: true, createdAt: true,
      retentionExemptUntil: true, retentionExemptReason: true, retentionReviewedAt: true,
      quarantinedAt: true, scheduledPurgeAt: true,
    },
  })

  const latestRows = await db
    .select({ candidateId: application.candidateId, latest: max(application.updatedAt) })
    .from(application)
    .where(eq(application.organizationId, orgId))
    .groupBy(application.candidateId)
  const latestByCandidate = new Map(latestRows.map(r => [r.candidateId, r.latest]))

  const now = new Date()
  const items = candidates.map((c) => {
    const { status, expiresAt } = computeRetentionState({
      latestProcessEnd: latestByCandidate.get(c.id) ?? null,
      candidateCreatedAt: c.createdAt,
      lastReviewedAt: c.retentionReviewedAt,
      retentionActivatedAt,
      retentionMonths,
      exemptUntil: c.retentionExemptUntil,
      now,
    })
    // Quarantined rows always surface regardless of computed status.
    const effectiveStatus = c.quarantinedAt ? 'quarantined' as const : status
    return {
      id: c.id,
      name: `${c.firstName} ${c.lastName}`.trim(),
      email: c.email,
      status: effectiveStatus,
      expiresAt,
      quarantinedAt: c.quarantinedAt,
      scheduledPurgeAt: c.scheduledPurgeAt,
      exemptUntil: c.retentionExemptUntil,
      exemptReason: c.retentionExemptReason,
    }
  })
  // Only show things needing attention: expiring / expired / quarantined / exempt.
  .filter(i => i.status !== 'active')

  return {
    cleanupEnabled: env.GDPR_CLEANUP_ENABLED,
    retentionEnabled: settings?.retentionEnabled ?? false,
    retentionMonths,
    count: items.length,
    items,
  }
})
