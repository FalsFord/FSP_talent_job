import { describe, it, expect } from 'vitest'
import { z } from 'zod'

/**
 * SSO Provider API validation tests.
 *
 * These tests validate the Zod schemas used by the SSO provider API routes
 * (POST /api/sso/providers, DELETE /api/sso/providers/[id]).
 * They exercise input sanitization, domain validation, provider ID format,
 * and issuer URL handling — without requiring a running server.
 */

// ─────────────────────────────────────────────
// Mirror the validation schemas from the API routes
// to test them in isolation.
// ─────────────────────────────────────────────

const registerSsoSchema = z.object({
  providerId: z.string().min(1).max(64).regex(/^[a-z0-9-]+$/, 'Only lowercase alphanumeric and hyphens'),
  issuer: z.string().url().refine(
    (url) => url.startsWith('https://') || url.startsWith('http://'),
    'Issuer URL must use HTTPS (or HTTP for local development)',
  ),
  domain: z.string().min(1).max(253).regex(
    /^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/,
    'Must be a valid domain (e.g. company.com)',
  ),
  clientId: z.string().min(1),
  clientSecret: z.string().min(1),
})

const deleteSsoSchema = z.object({
  id: z.string().min(1),
})

describe('SSO Provider registration schema', () => {
  const validPayload = {
    providerId: 'acme-sso',
    issuer: 'https://login.acme.com',
    domain: 'acme.com',
    clientId: 'client-id-123',
    clientSecret: 'super-secret-value',
  }

  // ────────────────────────────────────
  // Happy path
  // ────────────────────────────────────
  it('accepts a valid registration payload', () => {
    const result = registerSsoSchema.safeParse(validPayload)
    expect(result.success).toBe(true)
  })

  it('accepts a subdomain (e.g. sso.company.co.uk)', () => {
    const result = registerSsoSchema.safeParse({
      ...validPayload,
      domain: 'sso.company.co.uk',
    })
    expect(result.success).toBe(true)
  })

  it('accepts various real-world issuer URLs', () => {
    const issuers = [
      'https://login.microsoftonline.com/tenant-id/v2.0',
      'https://acme.okta.com',
      'https://accounts.google.com',
      'https://keycloak.internal.company.com/realms/production',
      'https://auth.company.io',
    ]

    for (const issuer of issuers) {
      const result = registerSsoSchema.safeParse({ ...validPayload, issuer })
      expect(result.success, `Expected issuer "${issuer}" to be accepted`).toBe(true)
    }
  })

  // ────────────────────────────────────
  // Provider ID validation
  // ────────────────────────────────────
  describe('providerId', () => {
    it('rejects empty provider ID', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects provider ID with uppercase letters', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: 'Acme-SSO',
      })
      expect(result.success).toBe(false)
    })

    it('rejects provider ID with spaces', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: 'acme sso',
      })
      expect(result.success).toBe(false)
    })

    it('rejects provider ID with special characters', () => {
      const badIds = ['acme_sso', 'acme.sso', 'acme/sso', 'acme@sso', 'acme!sso']
      for (const providerId of badIds) {
        const result = registerSsoSchema.safeParse({ ...validPayload, providerId })
        expect(result.success, `Expected "${providerId}" to be rejected`).toBe(false)
      }
    })

    it('rejects provider ID longer than 64 characters', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: 'a'.repeat(65),
      })
      expect(result.success).toBe(false)
    })

    it('accepts provider ID with hyphens and numbers', () => {
      const goodIds = ['acme-sso', 'my-company-123', 'sso-1', 'a', 'a-b-c-d']
      for (const providerId of goodIds) {
        const result = registerSsoSchema.safeParse({ ...validPayload, providerId })
        expect(result.success, `Expected "${providerId}" to be accepted`).toBe(true)
      }
    })
  })

  // ────────────────────────────────────
  // Domain validation
  // ────────────────────────────────────
  describe('domain', () => {
    it('rejects empty domain', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects single-label domains (no TLD)', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: 'localhost',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domains with protocols', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: 'https://company.com',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domains with paths', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: 'company.com/path',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domains with port numbers', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: 'company.com:8080',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domains starting with hyphens', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: '-company.com',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domains longer than 253 characters', () => {
      // Build a domain that actually exceeds 253 chars (previous was only 247)
      const longDomain = `${'a'.repeat(60)}.${'b'.repeat(60)}.${'c'.repeat(60)}.${'d'.repeat(60)}.${'e'.repeat(10)}.com`
      expect(longDomain.length).toBeGreaterThan(253)
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: longDomain,
      })
      expect(result.success).toBe(false)
    })

    it('accepts standard corporate domains', () => {
      const goodDomains = [
        'company.com',
        'corp.example.co.uk',
        'my-company.io',
        'test123.org',
        'sub.domain.example.com',
      ]
      for (const domain of goodDomains) {
        const result = registerSsoSchema.safeParse({ ...validPayload, domain })
        expect(result.success, `Expected "${domain}" to be accepted`).toBe(true)
      }
    })
  })

  // ────────────────────────────────────
  // Issuer URL validation
  // ────────────────────────────────────
  describe('issuer', () => {
    it('rejects empty issuer', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        issuer: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects non-URL issuer', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        issuer: 'not-a-url',
      })
      expect(result.success).toBe(false)
    })

    it('rejects issuer without protocol', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        issuer: 'login.company.com',
      })
      expect(result.success).toBe(false)
    })
  })

  // ────────────────────────────────────
  // Client credentials validation
  // ────────────────────────────────────
  describe('client credentials', () => {
    it('rejects empty clientId', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        clientId: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects empty clientSecret', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        clientSecret: '',
      })
      expect(result.success).toBe(false)
    })
  })

  // ────────────────────────────────────
  // Injection / XSS vectors in fields
  // ────────────────────────────────────
  describe('security: injection resistance', () => {
    it('rejects domain with HTML/script injection', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: '<script>alert(1)</script>.com',
      })
      expect(result.success).toBe(false)
    })

    it('rejects providerId with path traversal characters', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: '../../../etc/passwd',
      })
      expect(result.success).toBe(false)
    })

    it('rejects issuer with javascript: protocol', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        issuer: 'javascript:alert(1)',
      })
      expect(result.success).toBe(false)
    })

    it('rejects domain with null bytes', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        domain: 'company\x00.com',
      })
      expect(result.success).toBe(false)
    })

    it('rejects SQL injection in providerId', () => {
      const result = registerSsoSchema.safeParse({
        ...validPayload,
        providerId: "'; DROP TABLE sso_provider; --",
      })
      expect(result.success).toBe(false)
    })
  })
})

describe('SSO Provider delete schema', () => {
  it('accepts a valid ID', () => {
    const result = deleteSsoSchema.safeParse({ id: 'provider-123' })
    expect(result.success).toBe(true)
  })

  it('rejects empty ID', () => {
    const result = deleteSsoSchema.safeParse({ id: '' })
    expect(result.success).toBe(false)
  })

  it('rejects missing ID', () => {
    const result = deleteSsoSchema.safeParse({})
    expect(result.success).toBe(false)
  })
})
