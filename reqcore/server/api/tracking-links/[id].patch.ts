import { eq, and } from 'drizzle-orm'
import { trackingLink } from '../../database/schema'
import { trackingLinkIdSchema, updateTrackingLinkSchema } from '../../utils/schemas/trackingLink'

/**
 * PATCH /api/tracking-links/:id
 * Update a tracking link (name, channel, UTM params, active status).
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { sourceTracking: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, trackingLinkIdSchema.parse)
  const body = await readValidatedBody(event, updateTrackingLinkSchema.parse)

  const existing = await db.query.trackingLink.findFirst({
    where: and(eq(trackingLink.id, id), eq(trackingLink.organizationId, orgId)),
    columns: { id: true },
  })

  if (!existing) {
    throw createError({ statusCode: 404, statusMessage: 'Tracking link not found' })
  }

  const [updated] = await db.update(trackingLink)
    .set({ ...body, updatedAt: new Date() })
    .where(and(eq(trackingLink.id, id), eq(trackingLink.organizationId, orgId)))
    .returning()

  return updated
})
