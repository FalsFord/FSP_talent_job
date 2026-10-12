import { eq, and, isNull, max } from 'drizzle-orm'
import { application, candidate, orgSettings } from '../../database/schema'
import { candidateIdParamSchema } from '../../utils/schemas/candidate'
import { loadPropertyEntriesForEntity } from '../../utils/properties'
import { computeRetentionState } from '../../utils/retention'

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['read'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, candidateIdParamSchema.parse)

  const result = await db.query.candidate.findFirst({
    where: and(
      eq(candidate.id, id),
      eq(candidate.organizationId, orgId),
      isNull(candidate.quarantinedAt),
    ),
    columns: {
      id: true,
      firstName: true,
      lastName: true,
      displayName: true,
      email: true,
      phone: true,
      gender: true,
      dateOfBirth: true,
      quickNotes: true,
      retentionExemptUntil: true,
      retentionReviewedAt: true,
      quarantinedAt: true,
      scheduledPurgeAt: true,
      createdAt: true,
      updatedAt: true,
    },
    with: {
      applications: {
        columns: { id: true, status: true, createdAt: true },
        with: {
          job: {
            columns: { id: true, title: true },
          },
        },
        orderBy: (application, { desc }) => [desc(application.createdAt)],
      },
      documents: {
        columns: { id: true, type: true, originalFilename: true, mimeType: true, parsedContent: true, createdAt: true },
        orderBy: (document, { desc }) => [desc(document.createdAt)],
      },
    },
  })

  if (!result) {
    throw createError({ statusCode: 404, statusMessage: 'Not found' })
  }

  // Replace heavy parsedContent with a lightweight `parsed` boolean
  const { documents, ...rest } = result

  const properties = await loadPropertyEntriesForEntity({
    organizationId: orgId,
    entityType: 'candidate',
    entityId: result.id,
  })
  const [settings, latestProcess] = await Promise.all([
    db.query.orgSettings.findFirst({
      where: eq(orgSettings.organizationId, orgId),
      columns: {
        retentionEnabled: true,
        retentionMonths: true,
        retentionActivatedAt: true,
      },
    }),
    db
      .select({ latest: max(application.updatedAt) })
      .from(application)
      .where(and(
        eq(application.organizationId, orgId),
        eq(application.candidateId, id),
      ))
      .then(rows => rows[0]?.latest ?? null),
  ])
  const retention = settings?.retentionEnabled
    ? {
        enabled: true as const,
        ...computeRetentionState({
          latestProcessEnd: latestProcess,
          candidateCreatedAt: result.createdAt,
          lastReviewedAt: result.retentionReviewedAt,
          retentionActivatedAt: settings.retentionActivatedAt,
          retentionMonths: settings.retentionMonths,
          exemptUntil: result.retentionExemptUntil,
          now: new Date(),
        }),
        quarantinedAt: result.quarantinedAt,
        scheduledPurgeAt: result.scheduledPurgeAt,
      }
    : { enabled: false as const }

  const {
    retentionExemptUntil: _retentionExemptUntil,
    retentionReviewedAt: _retentionReviewedAt,
    quarantinedAt: _quarantinedAt,
    scheduledPurgeAt: _scheduledPurgeAt,
    ...publicCandidate
  } = rest

  return {
    ...publicCandidate,
    retention,
    documents: documents.map(({ parsedContent, ...doc }) => ({
      ...doc,
      parsed: parsedContent != null,
    })),
    properties,
  }
})
