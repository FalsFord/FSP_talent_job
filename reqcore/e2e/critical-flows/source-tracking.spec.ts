import { test, expect, declineAnalyticsConsent } from '../fixtures'

/**
 * Critical flow: Source tracking query parameters (?ref=, utm_*) propagate
 * through the public job browsing and application flow.
 *
 * When a candidate arrives via a tracking link, the redirect lands on
 * /jobs?ref=CODE (org-wide) or /jobs/:slug/apply?ref=CODE (job-scoped).
 * This test verifies that source params survive navigation from the job
 * listing → job detail → apply page, and are included in the POST body.
 *
 * Recruiter setup:
 * 1. Create a minimal job (no resume required, no custom questions)
 * 2. Publish and capture the slug
 *
 * Candidate flow:
 * 3. Open /jobs?ref=TRACK123&utm_source=linkedin (simulates org-wide tracking link)
 * 4. Click on the job → verify ref/utm params are forwarded to the detail page
 * 5. Click "Apply Now" → verify ref/utm params are forwarded to the apply page
 * 6. Submit the application → verify the POST body includes ref + utm_source
 */

const JOB_TITLE = 'Source Tracking Test Job'

test.describe('Source Tracking — Query Parameter Propagation', () => {
  test('ref and utm params propagate from job listing → detail → apply → submission', async ({ authenticatedPage, browser }, testInfo) => {
    const page = authenticatedPage

    // ── Step 1: Create and publish a minimal job ───────────────────────────────

    await page.goto('/dashboard/jobs/new')
    await page.waitForLoadState('networkidle')
    await page.getByLabel('Job title').waitFor({ state: 'visible', timeout: 15_000 })
    await page.getByLabel('Job title').fill(JOB_TITLE)

    // Step 1 → Step 2
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).first().waitFor({ state: 'attached', timeout: 10_000 })
    await expect(page.locator('form').getByRole('button', { name: 'Save & continue' }).first()).toBeEnabled({ timeout: 10_000 })
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).first().click()

    // Step 2: disable resume requirement
    const resumeRadioGroup = page.getByRole('radiogroup', { name: /Resume requirement/i })
    await resumeRadioGroup.waitFor({ state: 'visible', timeout: 10_000 })
    await resumeRadioGroup.getByRole('radio', { name: 'Off' }).click()

    // Step 2 → Step 3
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).first().click()

    // Step 3 → Step 4
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).first().waitFor({ state: 'visible', timeout: 10_000 })
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).first().click()

    // Step 4: Publish
    await expect(page.getByRole('heading', { name: /Ready to go\?/i })).toBeVisible({ timeout: 10_000 })
    const publishButton = page.locator('form').getByRole('button', { name: /Publish & copy link/i })
    await publishButton.waitFor({ state: 'visible', timeout: 10_000 })
    await publishButton.click()

    await expect(page.getByRole('heading', { name: 'Your job is live!' })).toBeVisible({ timeout: 20_000 })

    // Capture the slug from the application link
    const applicationLink = await page.locator('input[readonly]').inputValue()
    const slugMatch = applicationLink.match(/\/jobs\/([^/]+)\/apply/)
    const jobSlug = slugMatch?.[1] ?? ''
    expect(jobSlug.length, 'Job slug must not be empty').toBeGreaterThan(0)

    // ── Step 2: Candidate navigates from job listing with tracking params ──────

    const candidateContext = await browser.newContext()
    await declineAnalyticsConsent(candidateContext)
    const candidatePage = await candidateContext.newPage()

    const REF_CODE = 'TRACK_E2E_123'
    const UTM_SOURCE = 'linkedin'

    // Simulate arriving via an org-wide tracking link → /jobs?ref=...&utm_source=...
    await candidatePage.goto(`/jobs?ref=${REF_CODE}&utm_source=${UTM_SOURCE}`)
    await candidatePage.waitForLoadState('networkidle')

    // Find the job listing and click on it
    const jobLink = candidatePage.getByRole('link', { name: JOB_TITLE }).first()
    await expect(jobLink).toBeVisible({ timeout: 15_000 })
    await jobLink.click()

    // ── Verify: job detail page URL contains ref + utm_source ──────────────────

    await candidatePage.waitForURL(`**/jobs/${jobSlug}**`, { waitUntil: 'commit', timeout: 10_000 })
    const detailUrl = new URL(candidatePage.url())
    expect(detailUrl.searchParams.get('ref'), 'ref param must survive navigation to job detail').toBe(REF_CODE)
    expect(detailUrl.searchParams.get('utm_source'), 'utm_source must survive navigation to job detail').toBe(UTM_SOURCE)

    // Click "Apply Now"
    await candidatePage.getByRole('link', { name: 'Apply Now' }).first().click()

    // ── Verify: apply page URL contains ref + utm_source ───────────────────────

    await candidatePage.waitForURL(`**/jobs/${jobSlug}/apply**`, { waitUntil: 'commit', timeout: 10_000 })
    const applyUrl = new URL(candidatePage.url())
    expect(applyUrl.searchParams.get('ref'), 'ref param must survive navigation to apply page').toBe(REF_CODE)
    expect(applyUrl.searchParams.get('utm_source'), 'utm_source must survive navigation to apply page').toBe(UTM_SOURCE)

    // ── Step 3: Fill and submit the application ────────────────────────────────

    const APPLICANT = {
      firstName: 'Tracking',
      lastName: 'Test',
      email: `tracking.test.${Date.now()}.r${testInfo.retry}@example.com`,
    }

    await candidatePage.getByRole('button', { name: /submit/i }).waitFor({ state: 'visible', timeout: 15_000 })
    await candidatePage.getByLabel('First name').fill(APPLICANT.firstName)
    await candidatePage.getByLabel('Last name').fill(APPLICANT.lastName)
    await candidatePage.getByLabel('Email').fill(APPLICANT.email)

    // Intercept the POST to verify the body includes source tracking params
    const [applyResponse] = await Promise.all([
      candidatePage.waitForResponse(
        resp =>
          resp.url().includes(`/api/public/jobs/${jobSlug}/apply`) &&
          resp.request().method() === 'POST',
        { timeout: 30_000 },
      ),
      candidatePage.getByRole('button', { name: /submit/i }).click(),
    ])

    // Verify 2xx response
    const status = applyResponse.status()
    expect(status, `Apply API returned ${status}`).toBeGreaterThanOrEqual(200)
    expect(status, `Apply API returned ${status}`).toBeLessThan(300)

    // Verify the POST body included the tracking params
    const requestBody = applyResponse.request().postDataJSON()
    expect(requestBody.ref, 'POST body must include ref code').toBe(REF_CODE)
    expect(requestBody.utmSource, 'POST body must include utmSource').toBe(UTM_SOURCE)

    // Verify confirmation page
    await candidatePage.waitForURL(`**/jobs/${jobSlug}/confirmation`, {
      waitUntil: 'commit',
      timeout: 15_000,
    })
    await expect(candidatePage.getByRole('heading', { name: 'Application Submitted!' })).toBeVisible()

    await candidatePage.close()
    await candidateContext.close()
  })
})
