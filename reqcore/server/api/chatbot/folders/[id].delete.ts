import { and, eq } from 'drizzle-orm'
import { z } from 'zod'
import { chatbotFolder } from '../../../database/schema'
import { requireChatbotAccess } from '../../../utils/chatbotAccess'

/**
 * DELETE /api/chatbot/folders/[id]
 *
 * Conversations inside the folder are kept; their `folderId` is set to null
 * automatically by the FK constraint.
 */
export default defineEventHandler(async (event) => {
  const session = await requireChatbotAccess(event)
  const orgId = session.session.activeOrganizationId
  const userId = session.user.id
  const { id } = await getValidatedRouterParams(event, z.object({ id: z.string().uuid() }).parse)

  const result = await db.delete(chatbotFolder)
    .where(and(
      eq(chatbotFolder.id, id),
      eq(chatbotFolder.organizationId, orgId),
      eq(chatbotFolder.userId, userId),
    ))
    .returning({ id: chatbotFolder.id })

  if (result.length === 0) {
    throw createError({ statusCode: 404, statusMessage: 'Folder not found.' })
  }

  return { success: true }
})
