import { eq, and } from 'drizzle-orm'
import { trackingLink } from '../../database/schema'
import { trackingLinkIdSchema } from '../../utils/schemas/trackingLink'

/**
 * GET /api/tracking-links/:id
 * Get a single tracking link by ID.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { sourceTracking: ['read'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, trackingLinkIdSchema.parse)

  const link = await db.query.trackingLink.findFirst({
    where: and(eq(trackingLink.id, id), eq(trackingLink.organizationId, orgId)),
  })

  if (!link) {
    throw createError({ statusCode: 404, statusMessage: 'Tracking link not found' })
  }

  return link
})
