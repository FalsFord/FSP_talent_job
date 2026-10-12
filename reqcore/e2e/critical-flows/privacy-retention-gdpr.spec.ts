import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import postgres from 'postgres'
import { test, expect, declineAnalyticsConsent } from '../fixtures'

type CreatedCandidate = {
  id: string
  firstName: string
  lastName: string
  email: string
}

type CreatedJob = {
  id: string
  slug: string
  title: string
}

function databaseUrl(): string {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL

  const envFile = readFileSync(join(process.cwd(), '.env'), 'utf8')
  const line = envFile
    .split(/\r?\n/)
    .find(entry => entry.trim().startsWith('DATABASE_URL='))
  const value = line?.slice(line.indexOf('=') + 1).trim().replace(/^(['"])(.*)\1$/, '$2')

  if (!value) {
    throw new Error('DATABASE_URL is required to prepare time-dependent retention test data')
  }
  return value
}

async function createCandidate(
  page: Parameters<Parameters<typeof test>[1]>[0]['page'],
  input: { firstName: string, lastName: string, email: string },
): Promise<CreatedCandidate> {
  const response = await page.request.post('/api/candidates', {
    data: {
      ...input,
      phone: '+47 900 00 000',
      quickNotes: 'Created for GDPR critical-flow coverage',
    },
  })
  expect(response.status()).toBe(201)
  return response.json()
}

async function createOpenJob(
  page: Parameters<Parameters<typeof test>[1]>[0]['page'],
  title: string,
): Promise<CreatedJob> {
  const response = await page.request.post('/api/jobs', {
    data: {
      title,
      description: 'A published role used to verify the applicant privacy notice.',
      location: 'Oslo, Norway',
      type: 'full_time',
      status: 'open',
      phoneRequirement: 'optional',
      requireResume: false,
      requireCoverLetter: false,
      autoScoreOnApply: false,
      questions: [],
      criteria: [],
    },
  })
  expect(response.status()).toBe(201)
  return response.json()
}

async function backdateForRetention(candidateIds: string[]) {
  const sql = postgres(databaseUrl(), { max: 1 })
  const oldDate = new Date()
  oldDate.setFullYear(oldDate.getFullYear() - 3)

  try {
    await sql`
      update candidate
      set created_at = ${oldDate}, updated_at = ${oldDate}
      where id in ${sql(candidateIds)}
    `
    await sql`
      update org_settings
      set retention_activated_at = ${oldDate}
      where organization_id = (
        select organization_id from candidate where id = ${candidateIds[0]}
      )
    `
  }
  finally {
    await sql.end()
  }
}

test.describe('Privacy, retention, and GDPR critical flows', () => {
  test('saved policy is persisted and shown on the public application form', async ({ authenticatedPage, browser }) => {
    const page = authenticatedPage
    const jobTitle = `Privacy Notice Role ${Date.now()}`
    const notice = 'We use your application data only to assess your candidacy and meet recruitment obligations.'
    const policyUrl = 'https://example.com/recruitment-privacy'
    const contactEmail = 'privacy@example.com'

    await page.goto('/dashboard/settings/retention')
    await page.waitForLoadState('networkidle')

    const policySection = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Retention policy' }),
    })
    await policySection.getByRole('checkbox', { name: 'Enable automated retention' }).check()
    await policySection.locator('input[type="text"]').nth(0).fill('18')
    await policySection.locator('input[type="text"]').nth(1).fill('45')
    await page.getByPlaceholder('https://example.com/privacy').fill(policyUrl)
    await page.getByPlaceholder('privacy@example.com').fill(contactEmail)
    await page.getByPlaceholder(/We process your application data/).fill(notice)

    const settingsResponse = page.waitForResponse(response =>
      response.request().method() === 'PATCH'
      && new URL(response.url()).pathname === '/api/org-settings',
    )
    await page.getByRole('button', { name: 'Save changes' }).click()
    expect((await settingsResponse).status()).toBe(200)
    await expect(page.getByRole('button', { name: 'Saved!' })).toBeVisible()

    await page.reload()
    await expect(policySection.getByRole('checkbox', { name: 'Enable automated retention' })).toBeChecked()
    await expect(policySection.locator('input[type="text"]').nth(0)).toHaveValue('18')
    await expect(policySection.locator('input[type="text"]').nth(1)).toHaveValue('45')
    await expect(page.getByPlaceholder('https://example.com/privacy')).toHaveValue(policyUrl)
    await expect(page.getByPlaceholder('privacy@example.com')).toHaveValue(contactEmail)
    await expect(page.getByPlaceholder(/We process your application data/)).toHaveValue(notice)

    const job = await createOpenJob(page, jobTitle)
    const applicantContext = await browser.newContext()
    await declineAnalyticsConsent(applicantContext)
    const applicantPage = await applicantContext.newPage()

    try {
      await applicantPage.goto(`/jobs/${job.slug}/apply`)
      await expect(applicantPage.getByRole('heading', { name: jobTitle })).toBeVisible()
      await expect(applicantPage.getByText(notice)).toBeVisible()
      await expect(applicantPage.getByRole('link', { name: 'Privacy policy' })).toHaveAttribute('href', policyUrl)
      await expect(applicantPage.getByRole('link', { name: `Contact: ${contactEmail}` }))
        .toHaveAttribute('href', `mailto:${contactEmail}`)
    }
    finally {
      await applicantContext.close()
    }
  })

  test('expired candidates can be held, quarantined, exported, restored, and erased', async ({ authenticatedPage }, testInfo) => {
    const page = authenticatedPage
    const suffix = `${Date.now()}-${testInfo.retry}`
    const restoreCandidate = await createCandidate(page, {
      firstName: 'Restore',
      lastName: 'Candidate',
      email: `restore-${suffix}@example.com`,
    })
    const eraseCandidate = await createCandidate(page, {
      firstName: 'Erase',
      lastName: 'Candidate',
      email: `erase-${suffix}@example.com`,
    })

    const settingsResponse = await page.request.patch('/api/org-settings', {
      data: {
        retentionEnabled: true,
        retentionMonths: 1,
        quarantineDays: 30,
      },
    })
    expect(settingsResponse.status()).toBe(200)
    await backdateForRetention([restoreCandidate.id, eraseCandidate.id])

    await page.goto('/dashboard/settings/retention')
    await page.waitForLoadState('networkidle')

    const restoreRow = page.getByRole('listitem').filter({
      hasText: `${restoreCandidate.firstName} ${restoreCandidate.lastName}`,
    })
    const eraseRow = page.getByRole('listitem').filter({
      hasText: `${eraseCandidate.firstName} ${eraseCandidate.lastName}`,
    })
    await expect(restoreRow.getByText('Expired', { exact: true })).toBeVisible()
    await expect(eraseRow.getByText('Expired', { exact: true })).toBeVisible()

    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('prompt')
      await dialog.accept('Active legal dispute')
    })
    await restoreRow.getByRole('button', { name: 'Add legal hold' }).click()
    await expect(restoreRow.getByText('Exempt', { exact: true })).toBeVisible()
    await expect(restoreRow.getByText(/Active legal dispute/)).toBeVisible()

    const blockedDeletion = await page.request.delete(`/api/candidates/${restoreCandidate.id}`)
    expect(blockedDeletion.status()).toBe(409)
    expect(await blockedDeletion.text()).toContain('legal hold')

    await restoreRow.getByRole('button', { name: 'Clear legal hold' }).click()
    await expect(restoreRow.getByText('Expired', { exact: true })).toBeVisible()

    const cleanupResponse = await page.request.post('/api/admin/retention-cleanup', {
      data: { dryRun: false, batchSize: 10 },
    })
    expect(cleanupResponse.status()).toBe(200)
    const cleanup = await cleanupResponse.json()
    expect(cleanup.enabled).toBe(true)
    expect(cleanup.quarantined).toBeGreaterThanOrEqual(2)

    await page.reload()
    await expect(restoreRow.getByText('Quarantined', { exact: true })).toBeVisible()
    await expect(eraseRow.getByText('Quarantined', { exact: true })).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await restoreRow.getByRole('button', { name: 'Export data' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`candidate-${restoreCandidate.id}-export.json`)
    const exportPath = await download.path()
    expect(exportPath).not.toBeNull()
    const exported = JSON.parse(readFileSync(exportPath!, 'utf8'))
    expect(exported.candidate).toMatchObject({
      id: restoreCandidate.id,
      email: restoreCandidate.email,
      firstName: restoreCandidate.firstName,
      lastName: restoreCandidate.lastName,
    })

    await restoreRow.getByRole('button', { name: 'Restore' }).click()
    await expect(restoreRow).toHaveCount(0)
    expect((await page.request.get(`/api/candidates/${restoreCandidate.id}`)).status()).toBe(200)

    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('prompt')
      await dialog.accept(`${eraseCandidate.firstName} ${eraseCandidate.lastName}`)
    })
    const erasureResponse = page.waitForResponse(response =>
      response.request().method() === 'DELETE'
      && new URL(response.url()).pathname === `/api/candidates/${eraseCandidate.id}`,
    )
    await eraseRow.getByRole('button', { name: 'Erase now' }).click()
    expect((await erasureResponse).status()).toBe(204)
    await expect(eraseRow).toHaveCount(0)
    expect((await page.request.get(`/api/candidates/${eraseCandidate.id}`)).status()).toBe(404)
  })
})
