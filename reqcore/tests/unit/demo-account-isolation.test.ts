import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = process.cwd()
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')

describe('demo account organization isolation', () => {
  it('forces server API auth helpers to reject non-demo active organizations', () => {
    expect(read('server/utils/demoOrg.ts')).toMatch(/export async function assertDemoAccountCanUseOrg/)
    expect(read('server/utils/requireAuth.ts')).toMatch(/assertDemoAccountCanUseOrg\(session\.user\.email,\s*activeOrganizationId\)/)
    expect(read('server/utils/requirePermission.ts')).toMatch(/assertDemoAccountCanUseOrg\(session\.user\.email,\s*activeOrganizationId\)/)
  })

  it('guards Better Auth organization routes for the shared demo identity', () => {
    const authRoute = read('server/api/auth/[...all].ts')

    expect(authRoute).toMatch(/normalizeDemoActiveOrganization/)
    expect(authRoute).toMatch(/filterDemoOrganizationResponse/)
    expect(authRoute).toMatch(/authPath !== '\/organization\/set-active'/)
    expect(authRoute).toMatch(/authPath !== '\/organization\/list'/)
    expect(authRoute).toMatch(/The demo account cannot modify organization memberships or settings/)
  })

  it('blocks demo users from discovering or joining real organizations', () => {
    expect(read('server/api/org-search/index.get.ts')).toMatch(/isDemoAccountEmail\(session\.user\.email\)/)
    expect(read('server/api/invite-links/accept.post.ts')).toMatch(/The demo account cannot join other organizations/)
    expect(read('server/api/join-requests/index.post.ts')).toMatch(/The demo account cannot request access/)
  })
})
