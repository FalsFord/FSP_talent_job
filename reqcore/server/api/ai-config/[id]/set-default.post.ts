import { and, eq, sql } from 'drizzle-orm'
import { z } from 'zod'
import { aiConfig } from '../../../database/schema'
import { setAiConfigDefaultSchema } from '../../../utils/schemas/scoring'

const paramsSchema = z.object({ id: z.string().min(1) })

/**
 * POST /api/ai-config/:id/set-default
 *
 * Atomically claims one or more "default" slots (chatbot, analysis) for this
 * configuration. Uses a single UPDATE per purpose that sets the flag to true
 * for the chosen row and false for every other row in the same organization,
 * so the "exactly one default per purpose" invariant is preserved even under
 * concurrent requests. The partial unique indexes on `is_default_chatbot` and
 * `is_default_analysis` provide a DB-level backstop.
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { scoring: ['create'] })
  const orgId = session.session.activeOrganizationId
  const { id } = await getValidatedRouterParams(event, paramsSchema.parse)
  const body = await readValidatedBody(event, setAiConfigDefaultSchema.parse)

  const existing = await db.query.aiConfig.findFirst({
    where: and(eq(aiConfig.id, id), eq(aiConfig.organizationId, orgId)),
    columns: { id: true },
  })
  if (!existing) throw createError({ statusCode: 404, statusMessage: 'AI configuration not found.' })

  await db.transaction(async (tx) => {
    if (body.purposes.includes('chatbot')) {
      await tx.update(aiConfig)
        .set({
          isDefaultChatbot: sql`${aiConfig.id} = ${id}`,
          updatedAt: new Date(),
        })
        .where(eq(aiConfig.organizationId, orgId))
    }
    if (body.purposes.includes('analysis')) {
      await tx.update(aiConfig)
        .set({
          isDefaultAnalysis: sql`${aiConfig.id} = ${id}`,
          updatedAt: new Date(),
        })
        .where(eq(aiConfig.organizationId, orgId))
    }
  })

  recordActivity({
    organizationId: orgId,
    actorId: session.user.id,
    action: 'updated',
    resourceType: 'aiConfig',
    resourceId: id,
    metadata: { setDefault: body.purposes },
  })

  return { success: true }
})
