import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { eraseCandidates } from '../../server/utils/erasure'

// ─────────────────────────────────────────────
// Build a configurable in-memory mock of the Nitro auto-imported `db` global.
// erasure.ts reads `db` and `deleteFromS3` as globals at call time, so stubbing
// globalThis is enough — no real database is touched.
// ─────────────────────────────────────────────
interface MockOpts {
  id?: string
  candidateExists?: boolean
  documents?: string[]
  applications?: string[]
  interviews?: string[]
  comments?: unknown[]
  properties?: unknown[]
  activityLogs?: unknown[]
  /** Retention fields returned by the candidate findFirst (for purge-guard tests). */
  quarantinedAt?: Date | null
  scheduledPurgeAt?: Date | null
  retentionExemptUntil?: Date | null
  /** When false, the atomic candidate delete matches 0 rows (simulates a mid-sweep reapplication). */
  candidateDeleted?: boolean
}

function makeDb(opts: MockOpts) {
  const selectResults = [opts.comments ?? [], opts.properties ?? [], opts.activityLogs ?? []]
  let selectIdx = 0
  const inserts: Record<string, unknown>[] = []
  const deletedRows = opts.candidateDeleted === false ? [] : [{ id: opts.id ?? 'c1' }]
  const txDelete = vi.fn(() => ({
    where: vi.fn(() => Object.assign(Promise.resolve(deletedRows), {
      returning: vi.fn(() => Promise.resolve(deletedRows)),
    })),
  }))
  const transaction = vi.fn(async (cb: (tx: unknown) => unknown) => cb({ delete: txDelete }))
  const insert = vi.fn(() => ({
    values: vi.fn((v: Record<string, unknown>) => { inserts.push(v); return Promise.resolve() }),
  }))

  const db = {
    query: {
      candidate: {
        findFirst: vi.fn(async () => (opts.candidateExists
          ? {
              id: opts.id ?? 'c1',
              quarantinedAt: opts.quarantinedAt ?? null,
              scheduledPurgeAt: opts.scheduledPurgeAt ?? null,
              retentionExemptUntil: opts.retentionExemptUntil ?? null,
            }
          : undefined)),
      },
      document: {
        findMany: vi.fn(async () =>
          (opts.documents ?? []).map((storageKey, index) => ({ id: `d${index + 1}`, storageKey })),
        ),
      },
      application: { findMany: vi.fn(async () => (opts.applications ?? []).map(id => ({ id }))) },
      interview: { findMany: vi.fn(async () => (opts.interviews ?? []).map(id => ({ id }))) },
    },
    select: vi.fn(() => ({
      from: vi.fn(() => ({ where: vi.fn(() => Promise.resolve(selectResults[selectIdx++])) })),
    })),
    transaction,
    insert,
  }
  return { db, transaction, txDelete, insert, inserts }
}

let deleteFromS3: ReturnType<typeof vi.fn>

afterEach(() => { vi.unstubAllGlobals() })

describe('eraseCandidates', () => {
  beforeEach(() => {
    deleteFromS3 = vi.fn(async () => {})
    vi.stubGlobal('deleteFromS3', deleteFromS3)
    // Re-provide the logger globals (afterEach unstubs everything, including
    // the ones from tests/setup.ts).
    vi.stubGlobal('logInfo', vi.fn())
    vi.stubGlobal('logWarn', vi.fn())
  })

  it('dry run touches nothing', async () => {
    const m = makeDb({ candidateExists: true, documents: ['k1'], comments: [{}, {}] })
    vi.stubGlobal('db', m.db)

    const report = await eraseCandidates('org1', ['c1'], { dryRun: true })

    expect(report.dryRun).toBe(true)
    expect(report.results[0].status).toBe('would_erase')
    expect(report.results[0].documents).toBe(1)
    expect(report.results[0].comments).toBe(2)
    expect(deleteFromS3).not.toHaveBeenCalled()
    expect(m.transaction).not.toHaveBeenCalled()
    expect(m.insert).not.toHaveBeenCalled()
  })

  it('reports not_found for a candidate missing in this org (tenant isolation + idempotency)', async () => {
    const m = makeDb({ candidateExists: false })
    vi.stubGlobal('db', m.db)

    const report = await eraseCandidates('org1', ['ghost'], {})

    expect(report.results[0].status).toBe('not_found')
    expect(deleteFromS3).not.toHaveBeenCalled()
    expect(m.transaction).not.toHaveBeenCalled()
  })

  it('deletes S3 objects BEFORE the DB graph, then erases', async () => {
    const m = makeDb({
      candidateExists: true,
      documents: ['k1', 'k2'],
      applications: ['a1'],
      interviews: ['i1'],
      comments: [{}, {}],
      properties: [{}],
    })
    vi.stubGlobal('db', m.db)

    const report = await eraseCandidates('org1', ['c1'], { actorId: 'u1' })

    expect(report.results[0].status).toBe('erased')
    expect(deleteFromS3).toHaveBeenCalledTimes(2)
    expect(m.transaction).toHaveBeenCalledTimes(1)
    // 4 polymorphic/graph deletes inside the transaction.
    expect(m.txDelete).toHaveBeenCalledTimes(4)
    expect(m.db.query.application.findMany).toHaveBeenCalledTimes(1)
    expect(m.db.query.interview.findMany).toHaveBeenCalledTimes(1)
    // S3 deletion happens before the DB transaction.
    expect(deleteFromS3.mock.invocationCallOrder[0])
      .toBeLessThan(m.transaction.mock.invocationCallOrder[0])
  })

  it('does NOT delete the DB graph when an S3 object fails (keeps key for retry)', async () => {
    const m = makeDb({ candidateExists: true, documents: ['k1', 'bad'] })
    vi.stubGlobal('db', m.db)
    deleteFromS3.mockRejectedValueOnce(new Error('S3 down'))

    const report = await eraseCandidates('org1', ['c1'], {})

    expect(report.results[0].status).toBe('skipped_s3_failure')
    expect(report.results[0].s3Failures).toBe(1)
    expect(m.transaction).not.toHaveBeenCalled()
    // A 'partial' audit row is still written.
    expect(m.inserts[0]?.result).toBe('partial')
  })

  it('writes a privacy-safe audit row containing NO candidate PII', async () => {
    const m = makeDb({ candidateExists: true, documents: ['k1'], comments: [{}], properties: [], activityLogs: [{}, {}] })
    vi.stubGlobal('db', m.db)

    await eraseCandidates('org1', ['c1'], { actorId: 'u1' })

    expect(m.inserts).toHaveLength(1)
    const audit = m.inserts[0]
    expect(Object.keys(audit).sort()).toEqual(
      ['action', 'actorId', 'candidateId', 'metadata', 'organizationId', 'result'],
    )
    expect(audit.action).toBe('erased')
    expect(audit.result).toBe('success')
    // Metadata holds only non-PII counts.
    const meta = audit.metadata as Record<string, unknown>
    for (const v of Object.values(meta)) {
      expect(typeof v === 'number' || typeof v === 'string').toBe(true)
    }
    // No PII keys leaked into the audit payload.
    const serialized = JSON.stringify(audit)
    expect(serialized).not.toMatch(/email|firstName|lastName|storageKey|@/i)
  })

  it('flags auditFailed (and does not throw) when the audit row cannot be written', async () => {
    const m = makeDb({ candidateExists: true, documents: ['k1'] })
    // Make the audit insert throw, but leave the erasure itself successful.
    m.db.insert = vi.fn(() => ({ values: vi.fn(() => Promise.reject(new Error('audit table down'))) }))
    vi.stubGlobal('db', m.db)
    vi.stubGlobal('logError', vi.fn())

    const report = await eraseCandidates('org1', ['c1'], { actorId: 'u1' })

    expect(report.results[0].status).toBe('erased')
    expect(report.results[0].auditFailed).toBe(true)
    expect((globalThis as Record<string, unknown>).logError).toHaveBeenCalled()
  })

  describe('requirePurgeEligible (reapplication race guard)', () => {
    const PAST = new Date('2026-01-01T00:00:00Z')
    const FUTURE = new Date('2999-01-01T00:00:00Z')
    const NOW = new Date('2026-06-20T00:00:00Z')

    it('skips (pre-check) when the candidate is no longer quarantined — touches nothing', async () => {
      // A reapplication cleared quarantinedAt before the sweep reached this candidate.
      const m = makeDb({ candidateExists: true, documents: ['k1'], quarantinedAt: null })
      vi.stubGlobal('db', m.db)

      const report = await eraseCandidates('org1', ['c1'], { requirePurgeEligible: true, now: NOW })

      expect(report.results[0].status).toBe('skipped_not_eligible')
      expect(report.skipped).toBe(1)
      expect(report.erased).toBe(0)
      expect(deleteFromS3).not.toHaveBeenCalled()
      expect(m.transaction).not.toHaveBeenCalled()
    })

    it('skips (pre-check) when the candidate is under an active legal hold', async () => {
      const m = makeDb({
        candidateExists: true,
        documents: ['k1'],
        quarantinedAt: PAST,
        scheduledPurgeAt: PAST,
        retentionExemptUntil: FUTURE,
      })
      vi.stubGlobal('db', m.db)

      const report = await eraseCandidates('org1', ['c1'], { requirePurgeEligible: true, now: NOW })

      expect(report.results[0].status).toBe('skipped_not_eligible')
      expect(deleteFromS3).not.toHaveBeenCalled()
      expect(m.transaction).not.toHaveBeenCalled()
    })

    it('rolls back the transaction when the atomic delete matches 0 rows (race lost mid-sweep)', async () => {
      // Pre-check passes, but a reapplication restores the candidate before the
      // transaction; the guarded candidate delete matches nothing and we roll back.
      const m = makeDb({
        candidateExists: true,
        documents: ['k1'],
        comments: [{}],
        quarantinedAt: PAST,
        scheduledPurgeAt: PAST,
        candidateDeleted: false,
      })
      vi.stubGlobal('db', m.db)

      const report = await eraseCandidates('org1', ['c1'], { requirePurgeEligible: true, now: NOW })

      expect(report.results[0].status).toBe('skipped_not_eligible')
      expect(m.transaction).toHaveBeenCalledTimes(1)
      // No success audit row written for a rolled-back erasure.
      expect(m.inserts).toHaveLength(0)
    })

    it('erases when still quarantined and past purge', async () => {
      const m = makeDb({
        candidateExists: true,
        documents: ['k1'],
        quarantinedAt: PAST,
        scheduledPurgeAt: PAST,
      })
      vi.stubGlobal('db', m.db)

      const report = await eraseCandidates('org1', ['c1'], { requirePurgeEligible: true, now: NOW })

      expect(report.results[0].status).toBe('erased')
      expect(m.transaction).toHaveBeenCalledTimes(1)
      expect(m.inserts[0]?.result).toBe('success')
    })
  })

  it('aggregates a multi-candidate report', async () => {
    // First exists, second is a ghost.
    const existing = makeDb({ candidateExists: true, documents: [] })
    vi.stubGlobal('db', existing.db)
    const report = await eraseCandidates('org1', ['c1'], {})
    expect(report.processed).toBe(1)
    expect(report.erased).toBe(1)
    expect(report.skipped).toBe(0)
  })
})
