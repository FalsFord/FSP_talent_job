import { and, desc, eq, isNull } from 'drizzle-orm'
import { job, propertyDefinition } from '../../database/schema'
import { createPropertyDefinitionSchema } from '../../utils/schemas/property'

/**
 * POST /api/properties
 * Create a new property definition.
 *
 * Requires `organization: ['update']` — only owners/admins can edit the schema.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const body = await readValidatedBody(event, createPropertyDefinitionSchema.parse)

  // Candidate properties are always org-global
  if (body.entityType === 'candidate' && body.jobId) {
    throw createError({
      statusCode: 422,
      statusMessage: 'Candidate properties cannot be scoped to a job',
    })
  }

  // If jobId provided, verify it belongs to this org
  if (body.jobId) {
    const j = await db.query.job.findFirst({
      where: and(eq(job.id, body.jobId), eq(job.organizationId, orgId)),
      columns: { id: true },
    })
    if (!j) {
      throw createError({ statusCode: 404, statusMessage: 'Job not found' })
    }
  }

  // Compute displayOrder = max + 1 within this scope
  const last = await db
    .select({ displayOrder: propertyDefinition.displayOrder })
    .from(propertyDefinition)
    .where(
      and(
        eq(propertyDefinition.organizationId, orgId),
        eq(propertyDefinition.entityType, body.entityType),
        body.jobId
          ? eq(propertyDefinition.jobId, body.jobId)
          : isNull(propertyDefinition.jobId),
      ),
    )
    .orderBy(desc(propertyDefinition.displayOrder))
    .limit(1)

  const nextOrder = (last[0]?.displayOrder ?? -1) + 1

  const [created] = await db.insert(propertyDefinition).values({
    organizationId: orgId,
    entityType: body.entityType,
    type: body.type,
    name: body.name,
    description: body.description ?? null,
    jobId: body.jobId ?? null,
    config: (body.config ?? null) as Record<string, unknown> | null,
    displayOrder: nextOrder,
  }).returning()

  recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'created',
    resourceType: 'property',
    resourceId: created!.id,
    metadata: { entityType: body.entityType, type: body.type, jobId: body.jobId ?? null },
  })

  return created
})
