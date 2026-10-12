import { and, eq } from 'drizzle-orm'
import { propertyDefinition } from '../../database/schema'
import { propertyIdParamSchema } from '../../utils/schemas/property'

/**
 * DELETE /api/properties/:id
 * Removes a property definition. All values cascade-delete via the FK.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, propertyIdParamSchema.parse)

  const [deleted] = await db
    .delete(propertyDefinition)
    .where(and(eq(propertyDefinition.id, id), eq(propertyDefinition.organizationId, orgId)))
    .returning({ id: propertyDefinition.id })

  if (!deleted) {
    throw createError({ statusCode: 404, statusMessage: 'Property not found' })
  }

  recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'deleted',
    resourceType: 'property',
    resourceId: id,
  })

  return { id }
})
