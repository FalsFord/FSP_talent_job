import { and, eq } from 'drizzle-orm'
import { z } from 'zod'
import { application, propertyDefinition, propertyValue } from '../../../../database/schema'
import {
  setPropertyValueSchema,
  validateValueForType,
  type PropertyType,
} from '../../../../utils/schemas/property'

const paramsSchema = z.object({ id: z.string().min(1), propId: z.string().min(1) })

/**
 * PUT /api/applications/:id/properties/:propId
 * Set a property value for an application. Body: { value: any }.
 * Pass `null` to clear the value (the `value` key is required).
 *
 * Requires `application: ['update']` — same gate as editing notes/status.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { application: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id, propId } = await getValidatedRouterParams(event, paramsSchema.parse)
  const { value } = await readValidatedBody(event, setPropertyValueSchema.parse)

  // Verify entity belongs to org
  const app = await db.query.application.findFirst({
    where: and(eq(application.id, id), eq(application.organizationId, orgId)),
    columns: { id: true, jobId: true },
  })
  if (!app) throw createError({ statusCode: 404, statusMessage: 'Application not found' })

  // Verify property belongs to org and is valid in this application's context
  const def = await db.query.propertyDefinition.findFirst({
    where: and(
      eq(propertyDefinition.id, propId),
      eq(propertyDefinition.organizationId, orgId),
    ),
  })
  if (!def) throw createError({ statusCode: 404, statusMessage: 'Property not found' })
  if (def.entityType !== 'application') {
    throw createError({ statusCode: 422, statusMessage: 'Property is not an application property' })
  }
  if (def.jobId && def.jobId !== app.jobId) {
    throw createError({
      statusCode: 422,
      statusMessage: 'Property is scoped to a different job',
    })
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
          eq(propertyValue.entityType, 'application'),
        ),
      )
    return { value: null }
  }

  // Upsert
  const [row] = await db
    .insert(propertyValue)
    .values({
      organizationId: orgId,
      propertyDefinitionId: propId,
      entityType: 'application',
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
