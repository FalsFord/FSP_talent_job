import { eq, and } from 'drizzle-orm'
import { propertyDefinition } from '../../database/schema'
import { propertyListQuerySchema, type PropertyEntityType } from '../../utils/schemas/property'
import { loadPropertyDefinitions } from '../../utils/properties'

/**
 * GET /api/properties
 * Returns property definitions visible in the requested context.
 *
 *  - ?entityType=candidate              → org-global candidate defs
 *  - ?entityType=application            → org-global application defs
 *  - ?entityType=application&jobId=X    → org-global + per-job defs for X
 *  - ?entityType=application&jobId=X&jobOnly=1 → ONLY per-job defs for X (schema editor)
 *
 * Reading is gated on `application: ['read']` because property definitions
 * are pure metadata and any user with pipeline access needs to render them.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { application: ['read'] })
  const orgId = session.session.activeOrganizationId

  const query = await getValidatedQuery(event, propertyListQuerySchema.parse)

  if (query.jobOnly) {
    if (!query.jobId || query.entityType !== 'application') {
      throw createError({
        statusCode: 400,
        statusMessage: 'jobOnly requires entityType=application and a jobId',
      })
    }
    const rows = await db
      .select()
      .from(propertyDefinition)
      .where(
        and(
          eq(propertyDefinition.organizationId, orgId),
          eq(propertyDefinition.entityType, 'application'),
          eq(propertyDefinition.jobId, query.jobId),
        ),
      )
      .orderBy(propertyDefinition.displayOrder, propertyDefinition.createdAt)
    return rows
  }

  if (!query.entityType) {
    // Return both candidate and application org-global defs
    const [candidateDefs, applicationDefs] = await Promise.all([
      loadPropertyDefinitions({ organizationId: orgId, entityType: 'candidate' }),
      loadPropertyDefinitions({ organizationId: orgId, entityType: 'application' }),
    ])
    return { candidate: candidateDefs, application: applicationDefs }
  }

  return loadPropertyDefinitions({
    organizationId: orgId,
    entityType: query.entityType as PropertyEntityType,
    jobId: query.jobId ?? null,
  })
})
