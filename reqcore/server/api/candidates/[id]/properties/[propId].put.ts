import { and, eq } from 'drizzle-orm'
import { z } from 'zod'
import { candidate, propertyDefinition, propertyValue } from '../../../../database/schema'
import {
  setPropertyValueSchema,
  validateValueForType,
  type PropertyType,
} from '../../../../utils/schemas/property'

const paramsSchema = z.object({ id: z.string().min(1), propId: z.string().min(1) })

/**
 * PUT /api/candidates/:id/properties/:propId
 * Set a property value for a candidate. Body: { value: any }. Passing null clears.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id, propId } = await getValidatedRouterParams(event, paramsSchema.parse)
  const { value } = await readValidatedBody(event, setPropertyValueSchema.parse)

  const cand = await db.query.candidate.findFirst({
    where: and(eq(candidate.id, id), eq(candidate.organizationId, orgId)),
    columns: { id: true },
  })
  if (!cand) throw createError({ statusCode: 404, statusMessage: 'Candidate not found' })

  const def = await db.query.propertyDefinition.findFirst({
    where: and(
      eq(propertyDefinition.id, propId),
      eq(propertyDefinition.organizationId, orgId),
    ),
  })
  if (!def) throw createError({ statusCode: 404, statusMessage: 'Property not found' })
  if (def.entityType !== 'candidate') {
    throw createError({ statusCode: 422, statusMessage: 'Property is not a candidate property' })
  }

  const normalized = validateValueForType(def.type as PropertyType, value, def.config)

  if (normalized === null) {
    await db
      .delete(propertyValue)
      .where(
        and(
          eq(propertyValue.organizationId, orgId),
          eq(propertyValue.propertyDefinitionId, propId),
          eq(propertyValue.entityId, id),
          eq(propertyValue.entityType, 'candidate'),
        ),
      )
    return { value: null }
  }

  const [row] = await db
    .insert(propertyValue)
    .values({
      organizationId: orgId,
      propertyDefinitionId: propId,
      entityType: 'candidate',
      entityId: id,
      value: normalized as never,
    })
    .onConflictDoUpdate({
      target: [propertyValue.propertyDefinitionId, propertyValue.entityId],
      set: { value: normalized as never, updatedAt: new Date() },
    })
    .returning({ value: propertyValue.value })

  return { value: row?.value ?? normalized }
})
