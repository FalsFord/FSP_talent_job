/**
 * ─────────────────────────────────────────────
 * GDPR retention — pure date/state computation
 * ─────────────────────────────────────────────
 *
 * No I/O here on purpose: every function is deterministic and unit-testable.
 * The cron ([server/api/admin/retention-cleanup.post.ts]) derives each
 * candidate's expiry from these helpers rather than storing a denormalized
 * date, so the schedule self-heals after new applications or status changes.
 */

export type RetentionStatus = 'active' | 'expiring' | 'expired' | 'exempt'

/**
 * Minimum days between enabling retention for an org and the first candidate
 * becoming eligible for quarantine. Guarantees admins a review window so
 * existing (already-old) data is never deleted the moment retention is turned on.
 */
export const RETENTION_REVIEW_WINDOW_DAYS = 30

/** Days before `expiresAt` that a candidate is surfaced as "expiring soon". */
export const RETENTION_EXPIRING_WINDOW_DAYS = 30

/** Add `months` calendar months to `date` (clamps to end-of-month). */
export function addMonths(date: Date, months: number): Date {
  const d = new Date(date.getTime())
  const targetMonth = d.getMonth() + months
  d.setMonth(targetMonth)
  // If the day overflowed (e.g. Jan 31 + 1mo), setMonth rolls into the next
  // month — pull back to the last day of the intended month.
  if (d.getMonth() !== ((targetMonth % 12) + 12) % 12) {
    d.setDate(0)
  }
  return d
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * 24 * 60 * 60 * 1000)
}

export interface RetentionInput {
  /** MAX(application.updatedAt) — when the latest recruitment process last moved. Null = never applied. */
  latestProcessEnd: Date | null
  /** Fallback anchor when the candidate has no applications. */
  candidateCreatedAt: Date
  /**
   * When an admin last manually reviewed/restored the candidate. When later than
   * the process/creation anchor, it RESETS the clock — the candidate gets a
   * fresh `retentionMonths` window from this date. This is what makes restoring
   * from quarantine durable: without it the next sweep would re-quarantine
   * immediately because the underlying anchor never changed.
   */
  lastReviewedAt?: Date | null
  /** When retention was first enabled for the org (anchors the review window). */
  retentionActivatedAt: Date | null
  retentionMonths: number
  /** Candidate's exemption expiry, if any. */
  exemptUntil: Date | null
  now: Date
  expiringWindowDays?: number
}

export interface RetentionState {
  status: RetentionStatus
  /** The instant the candidate becomes eligible for quarantine. */
  expiresAt: Date
}

/**
 * Derive a candidate's retention state.
 *
 * Expiry = (latest process end OR candidate creation) + retentionMonths,
 * floored at retentionActivatedAt + review window so freshly-enabled orgs
 * always get a grace period before anything expires.
 */
export function computeRetentionState(input: RetentionInput): RetentionState {
  const {
    latestProcessEnd,
    candidateCreatedAt,
    lastReviewedAt = null,
    retentionActivatedAt,
    retentionMonths,
    exemptUntil,
    now,
    expiringWindowDays = RETENTION_EXPIRING_WINDOW_DAYS,
  } = input

  // A manual review/restore resets the clock when it is the most recent anchor.
  const baseAnchor = latestProcessEnd ?? candidateCreatedAt
  const anchor = lastReviewedAt && lastReviewedAt > baseAnchor ? lastReviewedAt : baseAnchor
  let expiresAt = addMonths(anchor, retentionMonths)

  // Never expire before the org's review window elapses after enabling retention.
  if (retentionActivatedAt) {
    const reviewFloor = addDays(retentionActivatedAt, RETENTION_REVIEW_WINDOW_DAYS)
    if (expiresAt < reviewFloor) expiresAt = reviewFloor
  }

  let status: RetentionStatus
  if (exemptUntil && exemptUntil > now) {
    status = 'exempt'
  }
  else if (now >= expiresAt) {
    status = 'expired'
  }
  else if (now >= addDays(expiresAt, -expiringWindowDays)) {
    status = 'expiring'
  }
  else {
    status = 'active'
  }

  return { status, expiresAt }
}

/** True when a candidate may be permanently erased now (past purge & not exempt). */
export function isPurgeEligible(params: {
  scheduledPurgeAt: Date | null
  exemptUntil: Date | null
  now: Date
}): boolean {
  const { scheduledPurgeAt, exemptUntil, now } = params
  if (exemptUntil && exemptUntil > now) return false
  return scheduledPurgeAt !== null && now >= scheduledPurgeAt
}
