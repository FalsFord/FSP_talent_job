import { and, eq, inArray } from 'drizzle-orm'
import { propertyDefinition } from '../../database/schema'
import { reorderPropertiesSchema } from '../../utils/schemas/property'

/**
 * POST /api/properties/reorder
 * Body: { ids: string[] } — applied left-to-right as displayOrder=0..N.
 * All ids must belong to the same scope (entityType + jobId); we enforce
 * that here so partial/mixed lists can't rewrite displayOrder across
 * unrelated definitions.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { ids } = await readValidatedBody(event, reorderPropertiesSchema.parse)
  if (ids.length === 0) return { ok: true }

  // Verify all ids belong to this org and share a single (entityType, jobId) scope
  const owned = await db
    .select({
      id: propertyDefinition.id,
      entityType: propertyDefinition.entityType,
      jobId: propertyDefinition.jobId,
    })
    .from(propertyDefinition)
    .where(
      and(
        eq(propertyDefinition.organizationId, orgId),
        inArray(propertyDefinition.id, ids),
      ),
    )
  if (owned.length !== ids.length) {
    throw createError({ statusCode: 404, statusMessage: 'One or more properties not found' })
  }

  const firstScope = owned[0]!
  const sameScope = owned.every(
    (r) => r.entityType === firstScope.entityType && r.jobId === firstScope.jobId,
  )
  if (!sameScope) {
    throw createError({
      statusCode: 400,
      statusMessage: 'All ids must belong to the same property scope',
    })
  }

  await db.transaction(async (tx) => {
    for (let i = 0; i < ids.length; i++) {
      await tx
        .update(propertyDefinition)
        .set({ displayOrder: i, updatedAt: new Date() })
        .where(
          and(
            eq(propertyDefinition.id, ids[i]!),
            eq(propertyDefinition.organizationId, orgId),
          ),
        )
    }
  })

  return { ok: true }
})
