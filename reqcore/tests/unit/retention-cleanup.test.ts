import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runRetentionCleanup } from '../../server/utils/retention-cleanup'

afterEach(() => vi.unstubAllGlobals())

describe('retention cleanup runner', () => {
  beforeEach(() => {
    vi.stubGlobal('logInfo', vi.fn())
    vi.stubGlobal('logWarn', vi.fn())
  })

  it('honors the instance-wide emergency switch without touching the database', async () => {
    const findMany = vi.fn()
    vi.stubGlobal('env', { GDPR_CLEANUP_ENABLED: false })
    vi.stubGlobal('db', { query: { orgSettings: { findMany } } })

    const result = await runRetentionCleanup({ source: 'scheduled_task' })

    expect(result.enabled).toBe(false)
    expect(result.orgsProcessed).toBe(0)
    expect(findMany).not.toHaveBeenCalled()
  })

  it('completes cleanly when no organization has opted in', async () => {
    const findMany = vi.fn(async () => [])
    vi.stubGlobal('env', { GDPR_CLEANUP_ENABLED: true })
    vi.stubGlobal('db', { query: { orgSettings: { findMany } } })

    const result = await runRetentionCleanup({
      source: 'interactive',
      dryRun: true,
      batchSize: 10,
    })

    expect(result).toMatchObject({
      enabled: true,
      dryRun: true,
      orgsProcessed: 0,
      quarantined: 0,
      erased: 0,
      skipped: 0,
      remainingEligible: 0,
      batchExhausted: false,
    })
  })
})
