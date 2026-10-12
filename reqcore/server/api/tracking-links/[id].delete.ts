import { eq, and } from 'drizzle-orm'
import { trackingLink } from '../../database/schema'
import { trackingLinkIdSchema } from '../../utils/schemas/trackingLink'

/**
 * DELETE /api/tracking-links/:id
 * Delete a tracking link. Existing application sources referencing
 * this link will have their trackingLinkId set to null (FK on delete set null).
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { sourceTracking: ['delete'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, trackingLinkIdSchema.parse)

  const existing = await db.query.trackingLink.findFirst({
    where: and(eq(trackingLink.id, id), eq(trackingLink.organizationId, orgId)),
    columns: { id: true },
  })

  if (!existing) {
    throw createError({ statusCode: 404, statusMessage: 'Tracking link not found' })
  }

  await db.delete(trackingLink)
    .where(and(eq(trackingLink.id, id), eq(trackingLink.organizationId, orgId)))

  setResponseStatus(event, 204)
  return null
})
