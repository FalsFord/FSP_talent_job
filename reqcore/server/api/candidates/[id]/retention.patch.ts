/**
 * PATCH /api/candidates/:id/retention
 *
 * Set or clear a documented retention exemption (temporary legal hold).
 * Body: { exemptUntil: ISO string | null, reason?: string }
 *   - exemptUntil in the future → candidate is skipped by automated erasure.
 *   - exemptUntil null → clears the exemption.
 */
import { z } from 'zod'
import { eq, and } from 'drizzle-orm'
import { candidate } from '../../../database/schema'
import { candidateIdParamSchema } from '../../../utils/schemas/candidate'
import { recordRetentionAudit } from '../../../utils/erasure'

const bodySchema = z.object({
  exemptUntil: z.string().datetime().nullable(),
  reason: z.string().max(500).optional(),
})
  // A legal hold must expire in the future and carry a documented reason.
  // Clearing a hold (exemptUntil: null) needs neither.
  .refine(b => b.exemptUntil === null || new Date(b.exemptUntil) > new Date(), {
    path: ['exemptUntil'],
    message: 'exemptUntil must be in the future',
  })
  .refine(b => b.exemptUntil === null || (b.reason != null && b.reason.trim().length > 0), {
    path: ['reason'],
    message: 'A reason is required when placing a legal hold',
  })

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { candidate: ['delete'] })
  const orgId = session.session.activeOrganizationId

  const { id } = await getValidatedRouterParams(event, candidateIdParamSchema.parse)
  const body = await readValidatedBody(event, bodySchema.parse)

  const exemptUntil = body.exemptUntil ? new Date(body.exemptUntil) : null

  const [updated] = await db.update(candidate)
    .set({
      retentionExemptUntil: exemptUntil,
      retentionExemptReason: exemptUntil ? (body.reason ?? null) : null,
      updatedAt: new Date(),
    })
    .where(and(eq(candidate.id, id), eq(candidate.organizationId, orgId)))
    .returning({ id: candidate.id })

  if (!updated) {
    throw createError({ statusCode: 404, statusMessage: 'Not found' })
  }

  await recordRetentionAudit(orgId, id, exemptUntil ? 'exempted' : 'unexempted', 'success', session.user.id, {})
  await recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'updated',
    resourceType: 'candidate',
    resourceId: id,
    metadata: {
      retentionAction: exemptUntil ? 'legal_hold_added' : 'legal_hold_removed',
      ...(exemptUntil ? { exemptUntil: exemptUntil.toISOString() } : {}),
    },
  })

  return { id, exemptUntil }
})
