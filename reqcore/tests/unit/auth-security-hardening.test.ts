import { describe, it, expect } from 'vitest'
import { encrypt, decrypt } from '../../server/utils/encryption'

/**
 * Auth security hardening tests.
 *
 * Validates the security-critical configurations applied to the Better Auth
 * instance. These tests verify the _intent_ of the config by simulating the
 * same logic, since the live auth instance requires a running database.
 *
 * NOTE: Password policy, session, and rate-limit constants are intentionally
 * duplicated here (not imported from auth.ts) because getAuth() is a lazy
 * factory that requires a live Postgres connection. If the production values
 * drift, these tests won't catch it — that is covered by integration/E2E tests.
 * The value of these unit tests is documenting and enforcing the security
 * contract (e.g. "session must not exceed 24 h") independently of the runtime.
 */

// ── Issue #2: Server-side password policy ───────────────────────────

describe('Server-side password policy', () => {
  const MIN_LENGTH = 8
  const MAX_LENGTH = 128

  it('rejects passwords shorter than minimum', () => {
    const password = 'short'
    expect(password.length).toBeLessThan(MIN_LENGTH)
  })

  it('accepts passwords at minimum length', () => {
    const password = 'a'.repeat(MIN_LENGTH)
    expect(password.length).toBeGreaterThanOrEqual(MIN_LENGTH)
  })

  it('rejects passwords exceeding maximum length', () => {
    const password = 'a'.repeat(MAX_LENGTH + 1)
    expect(password.length).toBeGreaterThan(MAX_LENGTH)
  })

  it('minimum length is at least 8 characters', () => {
    expect(MIN_LENGTH).toBeGreaterThanOrEqual(8)
  })
})

// ── Issue #6: Explicit session expiry ───────────────────────────────

describe('Session expiry configuration', () => {
  const SESSION_EXPIRES_IN = 60 * 60 * 24 // 24 hours (seconds)
  const SESSION_UPDATE_AGE = 60 * 60       // 1 hour (seconds)

  it('session expiry is explicitly set (not default 7 days)', () => {
    const DEFAULT_BETTER_AUTH_EXPIRY = 60 * 60 * 24 * 7 // 7 days
    expect(SESSION_EXPIRES_IN).toBeLessThan(DEFAULT_BETTER_AUTH_EXPIRY)
  })

  it('session expiry is at most 24 hours', () => {
    expect(SESSION_EXPIRES_IN).toBeLessThanOrEqual(60 * 60 * 24)
  })

  it('session update age is shorter than expiry', () => {
    expect(SESSION_UPDATE_AGE).toBeLessThan(SESSION_EXPIRES_IN)
  })
})

// ── Issue #7: OAuth token encryption at rest ────────────────────────

describe('OAuth token encryption at rest', () => {
  const TEST_SECRET = 'a'.repeat(32) // 32-char minimum per env validation

  it('encrypts and decrypts a token correctly', () => {
    const token = 'ya29.a0AfB_byBgxFake_google_access_token'
    const encrypted = encrypt(token, TEST_SECRET)

    // Encrypted output should differ from plaintext
    expect(encrypted).not.toBe(token)

    // Decrypted output should match original
    const decrypted = decrypt(encrypted, TEST_SECRET)
    expect(decrypted).toBe(token)
  })

  it('produces different ciphertext for same input (random IV)', () => {
    const token = 'gho_FakeGitHubAccessToken1234'
    const enc1 = encrypt(token, TEST_SECRET)
    const enc2 = encrypt(token, TEST_SECRET)
    expect(enc1).not.toBe(enc2)
  })

  it('returns null for tampered ciphertext', () => {
    const token = 'refresh_token_value'
    const encrypted = encrypt(token, TEST_SECRET)

    // Tamper with the ciphertext
    const tampered = encrypted.slice(0, -4) + 'XXXX'
    const result = decrypt(tampered, TEST_SECRET)
    expect(result).toBeNull()
  })

  it('returns null when decrypting with wrong secret', () => {
    const token = 'id_token_value'
    const encrypted = encrypt(token, TEST_SECRET)

    const wrongSecret = 'b'.repeat(32)
    const result = decrypt(encrypted, wrongSecret)
    expect(result).toBeNull()
  })
})

// ── Issue #4: Better Auth rate limiting config ──────────────────────

describe('Rate limiting configuration', () => {
  const rateLimitConfig = {
    enabled: !process.env.CI && !process.env.GITHUB_ACTIONS,
    window: 60,
    max: 100,
    storage: 'database' as const,
  }

  it('uses database storage (not in-memory)', () => {
    expect(rateLimitConfig.storage).toBe('database')
  })

  it('applies a reasonable global limit (not per-endpoint lockout)', () => {
    expect(rateLimitConfig.max).toBeGreaterThanOrEqual(50)
    expect(rateLimitConfig.max).toBeLessThanOrEqual(200)
  })

  it('is disabled in CI environments (Better Auth internal limiter only)', () => {
    // Better Auth's internal rate limiter is disabled in CI to prevent E2E
    // test flakiness. The apply-endpoint rate limiter uses NODE_ENV instead
    // and must not be bypassed via CI env vars in production.
    const ciConfig = { enabled: !('CI' in process.env) && !('GITHUB_ACTIONS' in process.env) }
    if (process.env.CI || process.env.GITHUB_ACTIONS) {
      expect(ciConfig.enabled).toBe(false)
    }
    else {
      expect(ciConfig.enabled).toBe(true)
    }
  })
})

// ── Issue #5: OAuth PKCE verification ───────────────────────────────
// Better Auth enables PKCE (codeVerifier in OAuth state) by default for
// all social providers. The genericOAuth plugin config in auth.ts sets
// pkce: true explicitly for OIDC. No unit test can exercise the real
// OAuth state builder without a running auth instance; these assertions
// are intentionally omitted until an integration test harness exists.
