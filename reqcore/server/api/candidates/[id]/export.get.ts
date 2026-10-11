/**
 * GET /api/candidates/:id/export
 *
 * Data-subject access export (GDPR Art. 15 / 20). Assembles the candidate's
 * full data graph as a downloadable JSON document. The org is the data
 * controller and is responsible for verifying the requester's identity before
 * sharing this — see DATA-RETENTION.md.
 */
import { eq, and } from 'drizzle-orm'
import { candidate, comment, propertyValue, activityLog } from '../../../database/schema'
import { candidateIdParamSchema } from '../../../utils/schemas/candidate'
import { recordRetentionAudit } from '../../../utils/erasure'

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['read'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, candidateIdParamSchema.parse)

  const record = await db.query.candidate.findFirst({
    where: and(eq(candidate.id, id), eq(candidate.organizationId, orgId)),
    with: {
      documents: true,
      applications: {
        with: {
          job: { columns: { id: true, title: true } },
          responses: true,
          interviews: true,
          criterionScores: true,
          // AI analysis output is personal data under Art. 15 (incl. any
          // automated-decision logic) and must be included in the export.
          analysisRuns: true,
          source: true,
        },
      },
    },
  })

  if (!record) {
    throw createError({ statusCode: 404, statusMessage: 'Not found' })
  }

  const [comments, properties, activity] = await Promise.all([
    db.select().from(comment).where(
      and(eq(comment.targetType, 'candidate'), eq(comment.targetId, id), eq(comment.organizationId, orgId)),
    ),
    db.select().from(propertyValue).where(
      and(eq(propertyValue.entityType, 'candidate'), eq(propertyValue.entityId, id), eq(propertyValue.organizationId, orgId)),
    ),
    db.select().from(activityLog).where(
      and(eq(activityLog.resourceType, 'candidate'), eq(activityLog.resourceId, id), eq(activityLog.organizationId, orgId)),
    ),
  ])

  await recordRetentionAudit(orgId, id, 'exported', 'success', session.user.id, {})

  setHeader(event, 'Content-Type', 'application/json')
  setHeader(event, 'Content-Disposition', `attachment; filename="candidate-${id}-export.json"`)

  return {
    exportedAt: new Date().toISOString(),
    candidate: record,
    comments,
    properties,
    activity,
    // Note: `candidate.documents` lists uploaded-file metadata (name, type,
    // storage key). The file *contents* (CVs, cover letters) are served
    // separately via the document download endpoints and are not inlined here.
    notice: 'Document file contents are available via their individual download links and are not embedded in this JSON.',
  }
})
