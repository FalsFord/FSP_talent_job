import { describe, expect, it } from 'vitest'
import { updateOrgSettingsSchema } from '../../server/utils/schemas/orgSettings'

describe('organization settings schema', () => {
  it('normalizes numeric form fields before validating them', () => {
    const result = updateOrgSettingsSchema.parse({
      retentionMonths: '24',
      quarantineDays: '30',
      privacyPolicyText: 'We process application data for recruitment.',
    })

    expect(result.retentionMonths).toBe(24)
    expect(result.quarantineDays).toBe(30)
  })

  it.each([
    { retentionMonths: '' },
    { retentionMonths: 'not-a-number' },
    { retentionMonths: '12.5' },
    { retentionMonths: '121' },
    { quarantineDays: '' },
    { quarantineDays: '-1' },
    { quarantineDays: '366' },
  ])('rejects invalid numeric form fields: %j', (payload) => {
    expect(updateOrgSettingsSchema.safeParse(payload).success).toBe(false)
  })
})
