/**
 * ─────────────────────────────────────────────
 * Candidate erasure service — the single source of truth for deletion
 * ─────────────────────────────────────────────
 *
 * Both manual deletion ([server/api/candidates/[id].delete.ts]) and the
 * automated retention cron ([server/api/admin/retention-cleanup.post.ts])
 * route through `eraseCandidates` so they produce identical results.
 *
 * Why this exists: a plain `DELETE FROM candidate` relies on FK cascades and
 * therefore LEAKS data — it orphans S3 objects and leaves behind the
 * polymorphic `property_value`, `comment`, and `activity_log` rows (which link
 * to candidates by id, with no FK). This service erases all of it.
 *
 * Ordering & safety:
 *   1. Delete S3 objects FIRST. If any fail, we DO NOT delete the DB rows —
 *      the `document.storageKey` is the only handle for a retry, so losing it
 *      would orphan the object forever. The candidate is left in place and the
 *      next cron run retries (idempotent).
 *   2. Then, in one transaction, delete the polymorphic rows and the candidate.
 *      The candidate delete cascades application → responses / interviews /
 *      criterion_score / analysis_run / application_source, and document rows.
 *
 * `db`, `deleteFromS3`, `logWarn`, `logInfo`, `logError` are Nitro auto-imports (globals).
 */
import { and, eq, inArray, isNotNull, isNull, lte, or } from 'drizzle-orm'
import {
  candidate,
  application,
  document,
  interview,
  propertyValue,
  comment,
  activityLog,
  retentionAudit,
} from '../database/schema'
import { isPurgeEligible } from './retention'

export interface ErasureOptions {
  /** When true, compute and report what would be deleted but mutate nothing. */
  dryRun?: boolean
  /** Triggering user id, or null/undefined for scheduled cron runs. */
  actorId?: string | null
  /** Additional privacy-safe context persisted with the erasure audit row. */
  auditMetadata?: Record<string, number | string>
  /**
   * Automated retention only. When true, erasure proceeds ONLY if the candidate
   * is still quarantined and purge-eligible (past purge, not exempt) — re-checked
   * in JS before any destructive work AND enforced atomically inside the delete
   * transaction. This closes the reapplication race: a data subject who reapplies
   * (which restores them out of quarantine and attaches a fresh application) after
   * the sweep selected them must NOT be erased. Manual deletion leaves this off and
   * erases unconditionally. See [server/utils/candidate-retention.ts].
   */
  requirePurgeEligible?: boolean
  /** Reference time for eligibility checks; defaults to now. Pass the sweep's `now`. */
  now?: Date
}

export type ErasureStatus =
  | 'erased'
  | 'skipped_s3_failure'
  | 'skipped_not_eligible'
  | 'not_found'
  | 'would_erase'

/** Internal sentinel: thrown to roll back the delete transaction when the atomic
 *  purge guard finds the candidate is no longer eligible (e.g. just reapplied). */
class PurgeNoLongerEligibleError extends Error {}

export interface ErasureResult {
  candidateId: string
  status: ErasureStatus
  documents: number
  comments: number
  properties: number
  activityLogs: number
  s3Failures: number
  /** True when the candidate was erased but its audit row could not be written. */
  auditFailed?: boolean
  error?: string
}

export interface ErasureReport {
  dryRun: boolean
  processed: number
  erased: number
  skipped: number
  results: ErasureResult[]
}

/**
 * Permanently erase one or more candidates and their entire data graph + S3 objects.
 * Org-scoped: only candidates belonging to `orgId` are touched. Idempotent and
 * safe to retry — already-gone candidates report `not_found` and missing S3
 * objects delete silently.
 */
export async function eraseCandidates(
  orgId: string,
  candidateIds: string[],
  opts: ErasureOptions = {},
): Promise<ErasureReport> {
  const dryRun = opts.dryRun ?? false
  const actorId = opts.actorId ?? null
  const requirePurgeEligible = opts.requirePurgeEligible ?? false
  const now = opts.now ?? new Date()
  const results: ErasureResult[] = []

  for (const candidateId of candidateIds) {
    results.push(await eraseOne(
      orgId,
      candidateId,
      dryRun,
      actorId,
      opts.auditMetadata ?? {},
      requirePurgeEligible,
      now,
    ))
  }

  return {
    dryRun,
    processed: results.length,
    erased: results.filter(r => r.status === 'erased' || r.status === 'would_erase').length,
    skipped: results.filter(r =>
      r.status === 'skipped_s3_failure'
      || r.status === 'skipped_not_eligible'
      || r.status === 'not_found',
    ).length,
    results,
  }
}

async function eraseOne(
  orgId: string,
  candidateId: string,
  dryRun: boolean,
  actorId: string | null,
  auditMetadata: Record<string, number | string>,
  requirePurgeEligible: boolean,
  now: Date,
): Promise<ErasureResult> {
  // Confirm the candidate exists in THIS org (tenant isolation + idempotency).
  const existing = await db.query.candidate.findFirst({
    where: and(eq(candidate.id, candidateId), eq(candidate.organizationId, orgId)),
    columns: {
      id: true,
      quarantinedAt: true,
      scheduledPurgeAt: true,
      retentionExemptUntil: true,
    },
  })

  if (!existing) {
    return blank(candidateId, 'not_found')
  }

  // Reapplication race, first line of defence: re-confirm eligibility in JS before
  // doing any destructive work. The atomic guard inside the transaction below is the
  // hard guarantee; this just shrinks the window in which S3 objects could be deleted
  // for a candidate that reapplied mid-sweep.
  if (requirePurgeEligible) {
    const stillEligible = existing.quarantinedAt !== null && isPurgeEligible({
      scheduledPurgeAt: existing.scheduledPurgeAt,
      exemptUntil: existing.retentionExemptUntil,
      now,
    })
    if (!stillEligible) {
      logInfo('retention.purge_skipped_not_eligible', { org_id: orgId, phase: 'pre_delete' })
      return blank(candidateId, 'skipped_not_eligible')
    }
  }

  // Gather everything tied to the candidate (org-scoped on every query).
  const docs = await db.query.document.findMany({
    where: and(eq(document.candidateId, candidateId), eq(document.organizationId, orgId)),
    columns: { id: true, storageKey: true },
  })
  const documentIds = docs.map(row => row.id)
  const applications = await db.query.application.findMany({
    where: and(eq(application.candidateId, candidateId), eq(application.organizationId, orgId)),
    columns: { id: true },
  })
  const applicationIds = applications.map(row => row.id)
  const interviews = applicationIds.length > 0
    ? await db.query.interview.findMany({
        where: and(
          eq(interview.organizationId, orgId),
          inArray(interview.applicationId, applicationIds),
        ),
        columns: { id: true },
      })
    : []
  const interviewIds = interviews.map(row => row.id)

  const commentScope = applicationIds.length > 0
    ? or(
        and(eq(comment.targetType, 'candidate'), eq(comment.targetId, candidateId)),
        and(eq(comment.targetType, 'application'), inArray(comment.targetId, applicationIds)),
      )
    : and(eq(comment.targetType, 'candidate'), eq(comment.targetId, candidateId))
  const propertyScope = applicationIds.length > 0
    ? or(
        and(eq(propertyValue.entityType, 'candidate'), eq(propertyValue.entityId, candidateId)),
        and(eq(propertyValue.entityType, 'application'), inArray(propertyValue.entityId, applicationIds)),
      )
    : and(eq(propertyValue.entityType, 'candidate'), eq(propertyValue.entityId, candidateId))
  const activityScopes = [
    and(eq(activityLog.resourceType, 'candidate'), eq(activityLog.resourceId, candidateId)),
    ...(applicationIds.length > 0
      ? [and(eq(activityLog.resourceType, 'application'), inArray(activityLog.resourceId, applicationIds))]
      : []),
    ...(interviewIds.length > 0
      ? [and(eq(activityLog.resourceType, 'interview'), inArray(activityLog.resourceId, interviewIds))]
      : []),
    ...(documentIds.length > 0
      ? [and(eq(activityLog.resourceType, 'document'), inArray(activityLog.resourceId, documentIds))]
      : []),
  ]
  const activityScope = activityScopes.length === 1 ? activityScopes[0]! : or(...activityScopes)

  const [commentRows, propertyRows, activityRows] = await Promise.all([
    db.select({ id: comment.id }).from(comment).where(
      and(eq(comment.organizationId, orgId), commentScope),
    ),
    db.select({ id: propertyValue.id }).from(propertyValue).where(
      and(eq(propertyValue.organizationId, orgId), propertyScope),
    ),
    db.select({ id: activityLog.id }).from(activityLog).where(
      and(eq(activityLog.organizationId, orgId), activityScope),
    ),
  ])

  const counts = {
    documents: docs.length,
    comments: commentRows.length,
    properties: propertyRows.length,
    activityLogs: activityRows.length,
  }

  if (dryRun) {
    return { candidateId, status: 'would_erase', s3Failures: 0, ...counts }
  }

  // ── Step 1: delete S3 objects first ──
  let s3Failures = 0
  for (const doc of docs) {
    try {
      await deleteFromS3(doc.storageKey)
    }
    catch (err) {
      s3Failures++
      logWarn('retention.s3_delete_failed', {
        org_id: orgId,
        error_message: err instanceof Error ? err.message : String(err),
      })
    }
  }

  // Abort DB deletion if any object failed — keep the storageKeys for a retry.
  if (s3Failures > 0) {
    const audited = await writeAudit(orgId, candidateId, 'erased', 'partial', actorId, {
      ...counts,
      s3Failures,
      ...auditMetadata,
    })
    return {
      candidateId,
      status: 'skipped_s3_failure',
      s3Failures,
      ...counts,
      auditFailed: !audited,
    }
  }

  // ── Step 2: delete the DB graph in one transaction ──
  // For automated retention, the candidate delete carries an atomic purge guard:
  // it only matches a row that is STILL quarantined, past purge, and not exempt.
  // If a reapplication restored the candidate after our pre-check, the delete
  // matches nothing and we throw to roll back the entire transaction — the
  // polymorphic deletes above are undone with it, so the restored candidate and
  // their new application survive intact.
  const purgeGuard = requirePurgeEligible
    ? and(
        isNotNull(candidate.quarantinedAt),
        lte(candidate.scheduledPurgeAt, now),
        or(isNull(candidate.retentionExemptUntil), lte(candidate.retentionExemptUntil, now)),
      )
    : undefined

  try {
    await db.transaction(async (tx) => {
      await tx.delete(comment).where(
        and(eq(comment.organizationId, orgId), commentScope),
      )
      await tx.delete(propertyValue).where(
        and(eq(propertyValue.organizationId, orgId), propertyScope),
      )
      await tx.delete(activityLog).where(
        and(eq(activityLog.organizationId, orgId), activityScope),
      )
      // Cascades application → responses / interviews / scores / analysis / source, and documents.
      const deleted = await tx.delete(candidate).where(
        and(eq(candidate.id, candidateId), eq(candidate.organizationId, orgId), purgeGuard),
      ).returning({ id: candidate.id })

      if (requirePurgeEligible && deleted.length === 0) {
        throw new PurgeNoLongerEligibleError()
      }
    })
  }
  catch (err) {
    if (err instanceof PurgeNoLongerEligibleError) {
      // Lost the race to a reapplication between the pre-check and the transaction.
      // DB is intact (rolled back). NOTE: S3 objects for the candidate's prior
      // documents were already deleted in Step 1; this residual window is tiny but
      // non-zero. The candidate record and any new application are preserved.
      logWarn('retention.purge_skipped_reapplied', { org_id: orgId, candidate_id: candidateId })
      return blank(candidateId, 'skipped_not_eligible')
    }
    throw err
  }

  const audited = await writeAudit(orgId, candidateId, 'erased', 'success', actorId, {
    ...counts,
    ...auditMetadata,
  })
  logInfo('retention.candidate_erased', { org_id: orgId, ...counts })

  return { candidateId, status: 'erased', s3Failures: 0, ...counts, auditFailed: !audited }
}

async function writeAudit(
  orgId: string,
  candidateId: string,
  action: 'erased' | 'quarantined' | 'restored' | 'exempted' | 'unexempted' | 'exported',
  result: string,
  actorId: string | null,
  metadata: Record<string, number | string>,
): Promise<boolean> {
  try {
    await db.insert(retentionAudit).values({
      organizationId: orgId,
      candidateId,
      action,
      result,
      actorId,
      metadata,
    })
    return true
  }
  catch (err) {
    // A missing audit trail for an irreversible erasure is a compliance problem,
    // not a warning — escalate to error so it is alerted on, and report back to
    // the caller (the result carries `auditFailed`) rather than swallowing it.
    logError('retention.audit_write_failed', {
      org_id: orgId,
      candidate_id: candidateId,
      action,
      error_message: err instanceof Error ? err.message : String(err),
    })
    return false
  }
}

/** Re-exported so endpoints can record quarantine/restore/exempt without duplicating the helper. */
export { writeAudit as recordRetentionAudit }

function blank(candidateId: string, status: ErasureStatus): ErasureResult {
  return { candidateId, status, documents: 0, comments: 0, properties: 0, activityLogs: 0, s3Failures: 0 }
}
