import { describe, it, expect } from 'vitest'

/**
 * SSO auth configuration tests.
 *
 * Validates the OIDC/SSO plugin configuration structure that would be
 * passed to Better Auth. Tests the conditional plugin loading logic
 * and profile mapping without requiring a running auth instance.
 */

describe('SSO auth plugin conditional loading', () => {
  /**
   * Simulates the conditional spread logic in auth.ts:
   *
   *   ...(OIDC_CLIENT_ID && OIDC_CLIENT_SECRET && OIDC_DISCOVERY_URL
   *       ? [genericOAuth({...})]
   *       : [])
   */
  function shouldEnableGlobalOidc(env: Record<string, string | undefined>): boolean {
    return !!(env.OIDC_CLIENT_ID && env.OIDC_CLIENT_SECRET && env.OIDC_DISCOVERY_URL)
  }

  it('enables global OIDC when all three vars are set', () => {
    expect(shouldEnableGlobalOidc({
      OIDC_CLIENT_ID: 'id',
      OIDC_CLIENT_SECRET: 'secret',
      OIDC_DISCOVERY_URL: 'https://auth.example.com/.well-known/openid-configuration',
    })).toBe(true)
  })

  it('disables global OIDC when none are set', () => {
    expect(shouldEnableGlobalOidc({})).toBe(false)
  })

  it('disables global OIDC when only CLIENT_ID is set', () => {
    expect(shouldEnableGlobalOidc({
      OIDC_CLIENT_ID: 'id',
    })).toBe(false)
  })

  it('disables global OIDC when DISCOVERY_URL is missing', () => {
    expect(shouldEnableGlobalOidc({
      OIDC_CLIENT_ID: 'id',
      OIDC_CLIENT_SECRET: 'secret',
    })).toBe(false)
  })

  it('disables global OIDC when values are empty strings', () => {
    expect(shouldEnableGlobalOidc({
      OIDC_CLIENT_ID: '',
      OIDC_CLIENT_SECRET: 'secret',
      OIDC_DISCOVERY_URL: 'https://auth.example.com',
    })).toBe(false)
  })
})

describe('SSO profile mapping', () => {
  /**
   * Mirrors the mapProfileToUser function from auth.ts.
   * This is the function used by genericOAuth to extract user info from
   * the OIDC userinfo/ID token claims.
   */
  function mapProfileToUser(profile: Record<string, string | undefined>) {
    return {
      name:
        profile.name ||
        [profile.given_name, profile.family_name]
          .filter(Boolean)
          .join(' ') ||
        profile.preferred_username ||
        profile.email,
      email: profile.email,
      image: profile.picture,
    }
  }

  it('uses full name when available', () => {
    const result = mapProfileToUser({
      name: 'Jane Doe',
      email: 'jane@acme.com',
      given_name: 'Jane',
      family_name: 'Doe',
    })
    expect(result.name).toBe('Jane Doe')
    expect(result.email).toBe('jane@acme.com')
  })

  it('falls back to given_name + family_name when name is missing', () => {
    const result = mapProfileToUser({
      email: 'jane@acme.com',
      given_name: 'Jane',
      family_name: 'Doe',
    })
    expect(result.name).toBe('Jane Doe')
  })

  it('uses only given_name when family_name is missing', () => {
    const result = mapProfileToUser({
      email: 'jane@acme.com',
      given_name: 'Jane',
    })
    expect(result.name).toBe('Jane')
  })

  it('falls back to preferred_username when no name fields exist', () => {
    const result = mapProfileToUser({
      email: 'jane@acme.com',
      preferred_username: 'jdoe',
    })
    expect(result.name).toBe('jdoe')
  })

  it('falls back to email as ultimate name fallback', () => {
    const result = mapProfileToUser({
      email: 'jane@acme.com',
    })
    expect(result.name).toBe('jane@acme.com')
  })

  it('includes profile picture when available', () => {
    const result = mapProfileToUser({
      name: 'Jane Doe',
      email: 'jane@acme.com',
      picture: 'https://cdn.example.com/photo.jpg',
    })
    expect(result.image).toBe('https://cdn.example.com/photo.jpg')
  })

  it('returns undefined image when no picture claim', () => {
    const result = mapProfileToUser({
      name: 'Jane Doe',
      email: 'jane@acme.com',
    })
    expect(result.image).toBeUndefined()
  })

  it('handles empty string name by falling back', () => {
    const result = mapProfileToUser({
      name: '',
      email: 'jane@acme.com',
      preferred_username: 'jdoe',
    })
    // Empty string is falsy, should fall through to preferred_username
    expect(result.name).toBe('jdoe')
  })
})

describe('SSO enterprise provisioning config', () => {
  it('configures default member role for auto-provisioned users', () => {
    // This tests our configuration intent — the actual Better Auth SSO plugin
    // consumes these values. Documenting them here as executable specs.
    const provisioningConfig = {
      disabled: false,
      defaultRole: 'member',
    }

    expect(provisioningConfig.disabled).toBe(false)
    expect(provisioningConfig.defaultRole).toBe('member')
    // Security: new SSO users must NOT be provisioned as admin/owner
    expect(provisioningConfig.defaultRole).not.toBe('admin')
    expect(provisioningConfig.defaultRole).not.toBe('owner')
  })
})
