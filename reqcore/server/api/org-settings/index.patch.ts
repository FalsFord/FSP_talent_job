import { eq } from 'drizzle-orm'
import { orgSettings } from '../../database/schema'
import { updateOrgSettingsSchema } from '../../utils/schemas/orgSettings'

/** Empty strings from form inputs become NULL for nullable text fields. */
function emptyToNull(v: string | null | undefined): string | null | undefined {
  if (v === undefined) return undefined
  if (v === null || v === '') return null
  return v
}

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { organization: ['update'] })
  const orgId = session.session.activeOrganizationId

  const body = await readValidatedBody(event, updateOrgSettingsSchema.parse)

  const existing = await db.query.orgSettings.findFirst({
    where: eq(orgSettings.organizationId, orgId),
    columns: { retentionActivatedAt: true },
  })

  // Stamp the activation time the first time retention is turned on — this
  // anchors the review window so existing data isn't deleted immediately.
  const retentionActivatedAt = body.retentionEnabled === true
    ? (existing?.retentionActivatedAt ?? new Date())
    : existing?.retentionActivatedAt ?? null

  const privacyPolicyUrl = emptyToNull(body.privacyPolicyUrl)
  const privacyContactEmail = emptyToNull(body.privacyContactEmail)
  const privacyPolicyText = emptyToNull(body.privacyPolicyText)

  const [result] = await db
    .insert(orgSettings)
    .values({
      organizationId: orgId,
      nameDisplayFormat: body.nameDisplayFormat ?? 'first_last',
      dateFormat: body.dateFormat ?? 'mdy',
      retentionEnabled: body.retentionEnabled ?? false,
      retentionMonths: body.retentionMonths ?? 24,
      quarantineDays: body.quarantineDays ?? 30,
      retentionActivatedAt,
      privacyPolicyUrl: privacyPolicyUrl ?? null,
      privacyPolicyText: privacyPolicyText ?? null,
      privacyContactEmail: privacyContactEmail ?? null,
    })
    .onConflictDoUpdate({
      target: orgSettings.organizationId,
      set: {
        ...(body.nameDisplayFormat !== undefined && { nameDisplayFormat: body.nameDisplayFormat }),
        ...(body.dateFormat !== undefined && { dateFormat: body.dateFormat }),
        ...(body.retentionEnabled !== undefined && { retentionEnabled: body.retentionEnabled }),
        ...(body.retentionMonths !== undefined && { retentionMonths: body.retentionMonths }),
        ...(body.quarantineDays !== undefined && { quarantineDays: body.quarantineDays }),
        retentionActivatedAt,
        ...(privacyPolicyUrl !== undefined && { privacyPolicyUrl }),
        ...(privacyPolicyText !== undefined && { privacyPolicyText }),
        ...(privacyContactEmail !== undefined && { privacyContactEmail }),
        updatedAt: new Date(),
      },
    })
    .returning({
      nameDisplayFormat: orgSettings.nameDisplayFormat,
      dateFormat: orgSettings.dateFormat,
      retentionEnabled: orgSettings.retentionEnabled,
      retentionMonths: orgSettings.retentionMonths,
      quarantineDays: orgSettings.quarantineDays,
      retentionActivatedAt: orgSettings.retentionActivatedAt,
      privacyPolicyUrl: orgSettings.privacyPolicyUrl,
      privacyPolicyText: orgSettings.privacyPolicyText,
      privacyContactEmail: orgSettings.privacyContactEmail,
    })

  if (!result) {
    throw createError({ statusCode: 500, statusMessage: 'Failed to save settings' })
  }

  logApiRequest(event, session, 'org_settings.updated', {})
  if (
    body.retentionEnabled !== undefined
    || body.retentionMonths !== undefined
    || body.quarantineDays !== undefined
  ) {
    await recordActivity({
      organizationId: orgId,
      actorId: session.user.id,
      action: 'updated',
      resourceType: 'organization',
      resourceId: orgId,
      metadata: {
        settingsArea: 'retention',
        retentionEnabled: result.retentionEnabled,
        retentionMonths: result.retentionMonths,
        quarantineDays: result.quarantineDays,
      },
    })
  }

  return result
})
