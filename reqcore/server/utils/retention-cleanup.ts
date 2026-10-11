import { and, asc, eq, isNotNull, isNull, lte, max } from 'drizzle-orm'
import { application, candidate, orgSettings } from '../database/schema'
import { eraseCandidates, recordRetentionAudit } from './erasure'
import { computeRetentionState, isPurgeEligible } from './retention'

export interface RetentionCleanupOptions {
  dryRun?: boolean
  batchSize?: number
  actorId?: string | null
  source?: 'scheduled_task' | 'cron_endpoint' | 'interactive'
}

export interface RetentionCleanupResult {
  enabled: boolean
  dryRun: boolean
  source: NonNullable<RetentionCleanupOptions['source']>
  orgsProcessed: number
  quarantined: number
  erased: number
  skipped: number
  auditFailures: number
  attempts: number
  remainingEligible: number
  batchExhausted: boolean
  perOrg: Array<{
    organizationId: string
    quarantined: number
    erased: number
    skipped: number
  }>
}

/**
 * Shared retention runner used by the Nitro scheduled task, external cron
 * endpoint, and interactive admin trigger.
 */
export async function runRetentionCleanup(
  options: RetentionCleanupOptions = {},
): Promise<RetentionCleanupResult> {
  const dryRun = options.dryRun ?? false
  const batchSize = Math.min(2000, Math.max(1, options.batchSize ?? 200))
  const actorId = options.actorId ?? null
  const source = options.source ?? 'scheduled_task'

  if (!env.GDPR_CLEANUP_ENABLED) {
    logWarn('retention.cleanup_disabled', { source })
    return {
      enabled: false,
      dryRun,
      source,
      orgsProcessed: 0,
      quarantined: 0,
      erased: 0,
      skipped: 0,
      auditFailures: 0,
      attempts: 0,
      remainingEligible: 0,
      batchExhausted: false,
      perOrg: [],
    }
  }

  const startedAt = Date.now()
  const now = new Date()
  logInfo('retention.cleanup_started', { source, dry_run: dryRun, batch_size: batchSize })

  const orgs = await db.query.orgSettings.findMany({
    where: eq(orgSettings.retentionEnabled, true),
    columns: {
      organizationId: true,
      retentionMonths: true,
      quarantineDays: true,
      retentionActivatedAt: true,
    },
  })

  let quarantined = 0
  let erased = 0
  let skipped = 0
  let auditFailures = 0
  let attempts = 0
  let remainingEligible = 0
  let remainingSuccessfulErasures = batchSize
  // Failed storage deletions must not permanently starve later candidates.
  // Bound retries per run while allowing the sweep to move past failures.
  let remainingAttempts = Math.max(batchSize * 3, batchSize + 20)
  const perOrg: RetentionCleanupResult['perOrg'] = []

  for (const org of orgs) {
    const orgId = org.organizationId
    const latestRows = await db
      .select({ candidateId: application.candidateId, latest: max(application.updatedAt) })
      .from(application)
      .where(eq(application.organizationId, orgId))
      .groupBy(application.candidateId)
    const latestByCandidate = new Map(latestRows.map(row => [row.candidateId, row.latest]))

    const activeCandidates = await db.query.candidate.findMany({
      where: and(eq(candidate.organizationId, orgId), isNull(candidate.quarantinedAt)),
      columns: {
        id: true,
        createdAt: true,
        retentionExemptUntil: true,
        retentionReviewedAt: true,
      },
    })

    let orgQuarantined = 0
    for (const currentCandidate of activeCandidates) {
      const { status } = computeRetentionState({
        latestProcessEnd: latestByCandidate.get(currentCandidate.id) ?? null,
        candidateCreatedAt: currentCandidate.createdAt,
        lastReviewedAt: currentCandidate.retentionReviewedAt,
        retentionActivatedAt: org.retentionActivatedAt,
        retentionMonths: org.retentionMonths,
        exemptUntil: currentCandidate.retentionExemptUntil,
        now,
      })
      if (status !== 'expired') continue

      if (dryRun) {
        orgQuarantined++
        quarantined++
        continue
      }

      const purgeAt = new Date(now.getTime() + org.quarantineDays * 24 * 60 * 60 * 1000)
      const [updated] = await db.update(candidate)
        .set({ quarantinedAt: now, scheduledPurgeAt: purgeAt })
        .where(and(
          eq(candidate.id, currentCandidate.id),
          eq(candidate.organizationId, orgId),
          isNull(candidate.quarantinedAt),
        ))
        .returning({ id: candidate.id })
      // A concurrent run may have quarantined or removed the candidate first.
      if (!updated) continue

      orgQuarantined++
      quarantined++
      const audited = await recordRetentionAudit(
        orgId,
        currentCandidate.id,
        'quarantined',
        'success',
        actorId,
        {},
      )
      if (!audited) auditFailures++
    }

    const quarantinedCandidates = await db.query.candidate.findMany({
      where: and(
        eq(candidate.organizationId, orgId),
        isNotNull(candidate.quarantinedAt),
        lte(candidate.scheduledPurgeAt, now),
      ),
      columns: { id: true, scheduledPurgeAt: true, retentionExemptUntil: true },
      orderBy: [asc(candidate.scheduledPurgeAt), asc(candidate.id)],
    })
    const eligible = quarantinedCandidates.filter(currentCandidate =>
      isPurgeEligible({
        scheduledPurgeAt: currentCandidate.scheduledPurgeAt,
        exemptUntil: currentCandidate.retentionExemptUntil,
        now,
      }),
    )

    let orgErased = 0
    let orgSkipped = 0
    for (const currentCandidate of eligible) {
      if (remainingSuccessfulErasures <= 0 || remainingAttempts <= 0) {
        remainingEligible++
        continue
      }

      attempts++
      remainingAttempts--
      const report = await eraseCandidates(orgId, [currentCandidate.id], {
        dryRun,
        actorId,
        // Atomically re-confirm quarantine/purge-eligibility at delete time so a
        // candidate who reapplied after selection is not erased. See [erasure.ts].
        requirePurgeEligible: true,
        now,
      })
      const result = report.results[0]
      if (!result) continue

      if (result.status === 'erased' || result.status === 'would_erase') {
        orgErased++
        erased++
        remainingSuccessfulErasures--
      }
      else {
        orgSkipped++
        skipped++
      }
      if (result.auditFailed) auditFailures++
    }

    perOrg.push({
      organizationId: orgId,
      quarantined: orgQuarantined,
      erased: orgErased,
      skipped: orgSkipped,
    })
  }

  const batchExhausted = remainingEligible > 0
  const durationMs = Date.now() - startedAt
  const logContext = {
    source,
    dry_run: dryRun,
    orgs: orgs.length,
    quarantined,
    erased,
    skipped,
    audit_failures: auditFailures,
    attempts,
    remaining_eligible: remainingEligible,
    batch_exhausted: batchExhausted,
    duration_ms: durationMs,
  }
  if (auditFailures > 0 || remainingEligible > 0) {
    logWarn('retention.cleanup_completed_with_warnings', logContext)
  }
  else {
    logInfo('retention.cleanup_completed', logContext)
  }

  return {
    enabled: true,
    dryRun,
    source,
    orgsProcessed: orgs.length,
    quarantined,
    erased,
    skipped,
    auditFailures,
    attempts,
    remainingEligible,
    batchExhausted,
    perOrg,
  }
}
