import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const settingsPage = readFileSync(
  resolve(process.cwd(), 'app/pages/dashboard/settings/index.vue'),
  'utf8',
)

describe('organization settings auth client errors', () => {
  it('does not treat Better Auth update errors as successful saves', () => {
    expect(settingsPage).toMatch(/const result = await authClient\.organization\.update/)
    expect(settingsPage).toMatch(/if \(result\.error\)[\s\S]*Failed to update organization/)
    expect(settingsPage.indexOf('if (result.error)')).toBeLessThan(
      settingsPage.indexOf("track('org_settings_saved')"),
    )
  })

  it('does not navigate away when Better Auth delete returns an error', () => {
    const deleteStart = settingsPage.indexOf('const result = await authClient.organization.delete')
    expect(deleteStart).toBeGreaterThanOrEqual(0)

    const deleteGuard = settingsPage.indexOf('if (result.error)', deleteStart)
    const deleteTrack = settingsPage.indexOf("track('org_deleted')", deleteStart)
    const deleteNavigate = settingsPage.indexOf("await navigateTo(localePath('/onboarding/create-org')", deleteStart)

    expect(deleteGuard).toBeGreaterThanOrEqual(0)
    expect(deleteTrack).toBeGreaterThanOrEqual(0)
    expect(deleteNavigate).toBeGreaterThanOrEqual(0)
    expect(deleteGuard).toBeLessThan(deleteTrack)
    expect(deleteTrack).toBeLessThan(deleteNavigate)
    expect(settingsPage.slice(deleteStart, deleteNavigate)).toContain('Failed to delete organization')
  })
})
