import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { recordRetentionAudit } = vi.hoisted(() => ({
  recordRetentionAudit: vi.fn(async () => true),
}))
vi.mock('../../server/utils/erasure', () => ({ recordRetentionAudit }))

import {
  findActiveCandidate,
  restoreCandidateForPublicApplication,
} from '../../server/utils/candidate-retention'

afterEach(() => vi.unstubAllGlobals())

describe('candidate retention lifecycle guards', () => {
  beforeEach(() => {
    vi.stubGlobal('logInfo', vi.fn())
  })

  it('finds only an active candidate through the scoped query', async () => {
    const findFirst = vi.fn(async () => ({ id: 'candidate-1' }))
    vi.stubGlobal('db', { query: { candidate: { findFirst } } })

    await expect(findActiveCandidate('org-1', 'candidate-1')).resolves.toEqual({
      id: 'candidate-1',
    })
    expect(findFirst).toHaveBeenCalledTimes(1)
  })

  it('restores a candidate on fresh public engagement and writes an audit event', async () => {
    const returning = vi.fn(async () => [{ id: 'candidate-1' }])
    const where = vi.fn(() => ({ returning }))
    const set = vi.fn(() => ({ where }))
    const update = vi.fn(() => ({ set }))
    vi.stubGlobal('db', { update })

    await expect(
      restoreCandidateForPublicApplication('org-1', 'candidate-1'),
    ).resolves.toBe(true)

    expect(set).toHaveBeenCalledWith(expect.objectContaining({
      quarantinedAt: null,
      scheduledPurgeAt: null,
      retentionReviewedAt: expect.any(Date),
    }))
    expect(recordRetentionAudit).toHaveBeenCalledWith(
      'org-1',
      'candidate-1',
      'restored',
      'success',
      null,
      { source: 'public_application' },
    )
  })
})
