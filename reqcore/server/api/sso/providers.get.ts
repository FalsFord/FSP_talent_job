import { eq } from 'drizzle-orm'
import { ssoProvider } from '~~/server/database/schema'

/**
 * GET /api/sso/providers — list SSO providers for the current organization.
 * Only org owners/admins should access this.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const providers = await db
    .select({
      id: ssoProvider.id,
      providerId: ssoProvider.providerId,
      issuer: ssoProvider.issuer,
      domain: ssoProvider.domain,
      organizationId: ssoProvider.organizationId,
    })
    .from(ssoProvider)
    .where(eq(ssoProvider.organizationId, orgId))

  return providers
})
