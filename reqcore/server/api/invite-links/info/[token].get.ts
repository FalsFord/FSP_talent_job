import { eq, and, isNull, gt } from 'drizzle-orm'
import { z } from 'zod'
import { inviteLink, organization, user } from '../../../database/schema'

/**
 * GET /api/invite-links/info/:token
 * Get public info about an invite link (for the accept page).
 * Returns minimal info: org name, role, creator name.
 * Does NOT require authentication — page needs to show info before sign-in.
 *
 * Security: Only exposes non-sensitive data (org name, role, creator name).
 * Token is validated but not returned.
 */
export default defineEventHandler(async (event) => {
  const { token } = await getValidatedRouterParams(
    event,
    z.object({ token: z.string().regex(/^[0-9a-f]{64}$/, 'Invalid invite token') }).parse,
  )

  const [link] = await db
    .select({
      role: inviteLink.role,
      expiresAt: inviteLink.expiresAt,
      maxUses: inviteLink.maxUses,
      useCount: inviteLink.useCount,
      orgName: organization.name,
      orgSlug: organization.slug,
      createdByName: user.name,
    })
    .from(inviteLink)
    .innerJoin(organization, eq(inviteLink.organizationId, organization.id))
    .leftJoin(user, eq(inviteLink.createdById, user.id))
    .where(
      and(
        eq(inviteLink.token, token),
        isNull(inviteLink.revokedAt),
        gt(inviteLink.expiresAt, new Date()),
      ),
    )
    .limit(1)

  if (!link) {
    throw createError({
      statusCode: 404,
      statusMessage: 'Invalid, expired, or revoked invite link',
    })
  }

  // Check if max uses reached
  if (link.maxUses !== null && link.useCount >= link.maxUses) {
    throw createError({
      statusCode: 410,
      statusMessage: 'This invite link has reached its maximum number of uses',
    })
  }

  return {
    organizationName: link.orgName,
    organizationSlug: link.orgSlug,
    role: link.role,
    invitedByName: link.createdByName,
    expiresAt: link.expiresAt,
  }
})
