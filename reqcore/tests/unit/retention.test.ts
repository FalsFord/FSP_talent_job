import { describe, it, expect } from 'vitest'
import {
  addMonths,
  computeRetentionState,
  isPurgeEligible,
  RETENTION_REVIEW_WINDOW_DAYS,
} from '../../server/utils/retention'

const DAY = 24 * 60 * 60 * 1000

describe('addMonths', () => {
  it('adds whole months', () => {
    expect(addMonths(new Date('2026-01-15T00:00:00Z'), 2).getMonth()).toBe(2) // March
  })

  it('clamps to end-of-month overflow (Jan 31 + 1mo → Feb 28)', () => {
    const result = addMonths(new Date('2026-01-31T00:00:00Z'), 1)
    expect(result.getMonth()).toBe(1) // February, not rolled into March
    // 2026 is not a leap year → Feb 28
    expect(result.getDate()).toBe(28)
  })
})

describe('computeRetentionState', () => {
  const base = {
    candidateCreatedAt: new Date('2020-01-01T00:00:00Z'),
    retentionActivatedAt: null,
    retentionMonths: 24,
    exemptUntil: null as Date | null,
  }

  it('is active well before expiry', () => {
    const { status } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2026-01-01T00:00:00Z'),
      now: new Date('2026-06-01T00:00:00Z'),
    })
    expect(status).toBe('active')
  })

  it('is expired well past expiry', () => {
    const { status } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2022-01-01T00:00:00Z'),
      now: new Date('2026-01-01T00:00:00Z'),
    })
    expect(status).toBe('expired')
  })

  it('is expiring inside the warning window', () => {
    const { status, expiresAt } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2024-01-01T00:00:00Z'), // +24mo → 2026-01-01
      now: new Date('2025-12-20T00:00:00Z'), // within 30d of expiry
    })
    expect(status).toBe('expiring')
    expect(expiresAt.getUTCFullYear()).toBe(2026)
  })

  it('exemption overrides an otherwise-expired candidate', () => {
    const { status } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2020-01-01T00:00:00Z'),
      now: new Date('2026-01-01T00:00:00Z'),
      exemptUntil: new Date('2027-01-01T00:00:00Z'),
    })
    expect(status).toBe('exempt')
  })

  it('falls back to candidate creation when there are no applications', () => {
    const { status } = computeRetentionState({
      ...base,
      latestProcessEnd: null,
      now: new Date('2026-01-01T00:00:00Z'), // 2020 + 24mo = 2022 → expired
    })
    expect(status).toBe('expired')
  })

  it('a manual review/restore resets the clock so an expired candidate is no longer expired', () => {
    const now = new Date('2026-06-01T00:00:00Z')
    // Anchor in 2020 → long expired with a 24mo window…
    const expired = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2020-01-01T00:00:00Z'),
      now,
    })
    expect(expired.status).toBe('expired')

    // …but stamping a recent review date moves the anchor forward, granting a
    // fresh 24-month window. This is what makes restore durable.
    const { status, expiresAt } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2020-01-01T00:00:00Z'),
      lastReviewedAt: now,
      now,
    })
    expect(status).toBe('active')
    expect(expiresAt.getTime()).toBeGreaterThan(now.getTime())
  })

  it('a stale review date (older than the process anchor) does not shorten retention', () => {
    const { expiresAt } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2026-01-01T00:00:00Z'),
      lastReviewedAt: new Date('2024-01-01T00:00:00Z'), // older than the process end
      now: new Date('2026-02-01T00:00:00Z'),
    })
    // Anchor stays at the (later) process end → expiry is 2028-01, not 2026-01.
    expect(expiresAt.getUTCFullYear()).toBe(2028)
  })

  it('never expires existing data immediately after enabling retention (review window)', () => {
    const now = new Date('2026-06-01T00:00:00Z')
    const { status, expiresAt } = computeRetentionState({
      ...base,
      latestProcessEnd: new Date('2019-01-01T00:00:00Z'), // long past
      retentionActivatedAt: now, // just turned on
      now,
    })
    // The key guarantee: not eligible for quarantine/erasure yet, and the
    // expiry sits at least a full review window in the future.
    expect(status).not.toBe('expired')
    expect(expiresAt.getTime()).toBeGreaterThanOrEqual(now.getTime() + RETENTION_REVIEW_WINDOW_DAYS * DAY - 1000)
  })
})

describe('isPurgeEligible', () => {
  const now = new Date('2026-06-01T00:00:00Z')

  it('true when past the purge date and not exempt', () => {
    expect(isPurgeEligible({ scheduledPurgeAt: new Date('2026-05-01T00:00:00Z'), exemptUntil: null, now })).toBe(true)
  })

  it('false before the purge date', () => {
    expect(isPurgeEligible({ scheduledPurgeAt: new Date('2026-07-01T00:00:00Z'), exemptUntil: null, now })).toBe(false)
  })

  it('false when never quarantined', () => {
    expect(isPurgeEligible({ scheduledPurgeAt: null, exemptUntil: null, now })).toBe(false)
  })

  it('false when exempt, even if past purge date', () => {
    expect(isPurgeEligible({
      scheduledPurgeAt: new Date('2026-05-01T00:00:00Z'),
      exemptUntil: new Date('2026-12-01T00:00:00Z'),
      now,
    })).toBe(false)
  })
})
