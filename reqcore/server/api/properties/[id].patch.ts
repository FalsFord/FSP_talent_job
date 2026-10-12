import { and, eq } from 'drizzle-orm'
import { propertyDefinition } from '../../database/schema'
import {
  propertyIdParamSchema,
  updatePropertyDefinitionSchema,
} from '../../utils/schemas/property'

/**
 * PATCH /api/properties/:id
 * Update a property definition (name, description, config, displayOrder).
 * Type and entityType are immutable.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, propertyIdParamSchema.parse)
  const body = await readValidatedBody(event, updatePropertyDefinitionSchema.parse)

  const [updated] = await db
    .update(propertyDefinition)
    .set({ ...body, updatedAt: new Date() })
    .where(and(eq(propertyDefinition.id, id), eq(propertyDefinition.organizationId, orgId)))
    .returning()

  if (!updated) {
    throw createError({ statusCode: 404, statusMessage: 'Property not found' })
  }

  recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'updated',
    resourceType: 'property',
    resourceId: id,
  })

  return updated
})
