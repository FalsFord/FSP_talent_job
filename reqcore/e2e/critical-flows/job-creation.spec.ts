import { test, expect } from '../fixtures'

/**
 * Critical flow: Recruiter creates and publishes a job.
 *
 * Steps:
 * 1. Sign up + create org (via authenticatedPage fixture)
 * 2. Navigate to "Create Job" page
 * 3. Fill in job details (title, description, location, type)
 * 4. Submit the job
 * 5. Verify the job appears in the job list
 * 6. Open the job and publish it (draft → open)
 * 7. Verify the job is visible on the public jobs page
 */

const JOB_TITLE = 'Senior QA Engineer'
const JOB_DESCRIPTION = 'We are looking for a senior QA engineer to lead our testing efforts.'
const JOB_LOCATION = 'Remote'
const QUESTION_LABEL = 'Which testing framework do you know best?'
const UPDATED_QUESTION_LABEL = 'Which browser testing framework do you know best?'

test.describe('Job Creation Flow', () => {
  test('wizard rejects malformed drafts, invalid questions, and duplicate submissions', async ({ authenticatedPage }) => {
    const page = authenticatedPage

    await page.evaluate(() => {
      localStorage.setItem('reqcore-job-draft', JSON.stringify({
        form: { title: '   ' },
        applicationForm: { questions: 'not-an-array' },
        scoringCriteria: [{ key: '__invalid__' }],
        currentStep: 99,
      }))
    })
    await page.goto('/dashboard/jobs/new')
    await page.waitForLoadState('networkidle')

    const title = page.getByLabel('Job title')
    await expect(title).toBeVisible()
    await expect(title).toHaveValue('')
    await title.fill('   ')
    await expect(page.locator('form').getByRole('button', { name: 'Save & continue' })).toBeDisabled()

    await title.fill('Robustness Test Engineer')
    const continueButton = page.locator('form').getByRole('button', { name: 'Save & continue' })
    await expect(continueButton).toBeEnabled()
    await continueButton.click()

    await page.getByRole('button', { name: 'Add a question', exact: true }).click()
    await page.getByLabel('Question').fill('Preferred test framework?')
    await page.getByLabel('Field Type').selectOption('single_select')
    await page.getByPlaceholder('Option 1').fill('Playwright')
    await page.getByRole('button', { name: 'Add option' }).click()
    await page.getByPlaceholder('Option 2').fill(' playwright ')
    await page.getByRole('button', { name: 'Add Question', exact: true }).click()
    await expect(page.getByText('Options must be unique')).toBeVisible()

    await page.getByPlaceholder('Option 2').fill('Cypress')
    await page.getByRole('button', { name: 'Add Question', exact: true }).click()
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).click()
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).click()

    let createRequests = 0
    page.on('request', (request) => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/jobs') createRequests++
    })
    await page.locator('form button').filter({ hasText: /^Save as draft/ }).click()

    await page.locator('form').evaluate((form: HTMLFormElement) => {
      form.requestSubmit()
      form.requestSubmit()
    })

    await page.waitForURL(/\/dashboard\/jobs(?:\?|$)/)
    expect(createRequests).toBe(1)
  })

  test('recruiter can configure the application form and publish a job', async ({ authenticatedPage }) => {
    const page = authenticatedPage
    const dismissFeedbackSurvey = async () => {
      await page.getByRole('button', { name: 'No thanks' }).click({ timeout: 2_000 }).catch(() => {})
    }

    // ── Navigate to Create Job ───────────────────────────
    await page.goto('/dashboard/jobs/new')
    await page.waitForLoadState('networkidle')
    await dismissFeedbackSurvey()

    // ── Step 1: Fill in job details ──────────────────────
    // Wait for the form to be fully hydrated before interacting
    await page.getByLabel('Job title').waitFor({ state: 'visible', timeout: 15_000 })
    await page.getByLabel('Job title').fill(JOB_TITLE)
    await page.getByLabel('Description').fill(JOB_DESCRIPTION)
    await page.getByLabel('Location').fill(JOB_LOCATION)

    // The persistent candidate preview should update as job details are entered.
    const preview = page.getByRole('complementary')
    await expect(preview.getByRole('heading', { name: JOB_TITLE })).toBeVisible()
    await expect(preview.getByText(JOB_LOCATION)).toBeVisible()

    await page.locator('form').getByRole('button', { name: 'Save & continue' }).waitFor({ state: 'attached', timeout: 10_000 })
    await expect(page.locator('form').getByRole('button', { name: 'Save & continue' })).toBeEnabled({ timeout: 10_000 })
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).click()

    // ── Step 2: Configure the application form ───────────
    await expect(page.getByText('Customize your application form')).toBeVisible()

    const resumeRequirement = page.getByRole('radiogroup', { name: 'Resume requirement' })
    await resumeRequirement.getByRole('radio', { name: 'Off' }).click()
    await expect(resumeRequirement.getByRole('radio', { name: 'Off' })).toBeChecked()
    await expect(preview.getByText('Resume / CV', { exact: false })).toHaveCount(0)

    const coverLetterRequirement = page.getByRole('radiogroup', { name: 'Cover letter requirement' })
    await coverLetterRequirement.getByRole('radio', { name: 'Required' }).click()
    await expect(coverLetterRequirement.getByRole('radio', { name: 'Required' })).toBeChecked()
    await expect(preview.getByLabel('Cover Letter')).toBeVisible()

    // Add a required single-select question and verify it appears in the preview.
    await page.getByRole('button', { name: 'Add a question', exact: true }).click()
    await page.getByLabel('Question').fill(QUESTION_LABEL)
    await page.getByLabel('Field Type').selectOption('single_select')
    await page.getByPlaceholder('Option 1').fill('Playwright')
    await page.getByRole('button', { name: 'Add option' }).click()
    await page.getByPlaceholder('Option 2').fill('Cypress')
    await page.getByLabel('Required', { exact: true }).check()
    await page.getByRole('button', { name: 'Add Question', exact: true }).click()

    await expect(page.getByText('1 question added')).toBeVisible()
    const previewQuestion = preview.getByLabel(QUESTION_LABEL)
    await expect(previewQuestion).toBeVisible()
    await expect(previewQuestion.getByRole('option', { name: 'Playwright' })).toHaveCount(1)
    await expect(previewQuestion.getByRole('option', { name: 'Cypress' })).toHaveCount(1)

    // Editing must update both the builder row and the candidate preview.
    await page.getByTitle('Edit').click()
    await page.getByLabel('Question').fill(UPDATED_QUESTION_LABEL)
    await page.getByRole('button', { name: 'Update', exact: true }).click()
    await expect(preview.getByLabel(UPDATED_QUESTION_LABEL)).toBeVisible()
    await expect(preview.getByLabel(QUESTION_LABEL)).toHaveCount(0)

    // The full draft preview opens in a new tab and uses the applicant-facing form.
    const previewPagePromise = page.waitForEvent('popup')
    await page.getByRole('button', { name: 'View preview' }).click()
    const previewPage = await previewPagePromise
    await previewPage.waitForLoadState('domcontentloaded')
    await expect(previewPage.getByText('Draft applicant preview')).toBeVisible()
    await expect(previewPage.getByRole('heading', { name: JOB_TITLE })).toBeVisible()
    await expect(previewPage.getByText(JOB_DESCRIPTION)).toBeVisible()
    await expect(previewPage.getByLabel('Cover Letter')).toBeVisible()
    await expect(previewPage.getByText('Resume / CV', { exact: false })).toHaveCount(0)
    await expect(previewPage.getByLabel(UPDATED_QUESTION_LABEL)).toBeVisible()
    await previewPage.close()

    // Device switching is part of the new persistent preview.
    const previewDevice = preview.getByRole('radiogroup', { name: 'Preview device' })
    await previewDevice.getByRole('radio', { name: 'Mobile' }).click()
    await expect(previewDevice.getByRole('radio', { name: 'Mobile' })).toBeChecked()

    await page.locator('form').getByRole('button', { name: 'Save & continue' }).waitFor({ state: 'attached', timeout: 10_000 })
    await expect(page.locator('form').getByRole('button', { name: 'Save & continue' })).toBeEnabled({ timeout: 10_000 })
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).click()

    // Step 3: Scoring criteria — skip (defaults are fine)
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).waitFor({ state: 'visible', timeout: 10_000 })
    await dismissFeedbackSurvey()
    await page.locator('form').getByRole('button', { name: 'Save & continue' }).click()

    // Step 4: Publish the job
    await expect(page.getByRole('heading', { name: /Ready to go\?/i })).toBeVisible({ timeout: 10_000 })
    const publishButton = page.locator('form').getByRole('button', { name: /Publish & copy link/i })
    await publishButton.waitFor({ state: 'visible', timeout: 10_000 })
    await dismissFeedbackSurvey()
    await publishButton.click()

    // ── Verify the success state ("Your job is live!") ───
    await expect(page.getByRole('heading', { name: 'Your job is live!' })).toBeVisible({ timeout: 20_000 })

    // ── Extract job slug from the application link ────────
    const applicationLink = await page.locator('input[readonly]').inputValue()
    expect(applicationLink).toMatch(/\/jobs\/[^/]+\/apply(?:$|[?#])/)
    const slugMatch = applicationLink.match(/\/jobs\/([^/]+)\/apply(?:$|[?#])/)
    const jobSlug = slugMatch?.[1] ?? ''
    expect(jobSlug.length, 'Job slug must not be empty').toBeGreaterThan(0)

    // ── Verify on public jobs page ───────────────────────
    await page.goto(`/jobs/${jobSlug}`)
    await expect(page.getByRole('heading', { name: JOB_TITLE })).toBeVisible()
    await expect(page.getByText(JOB_LOCATION)).toBeVisible()

    // Verify the "Apply" link/button is present (use .first() because the page has two apply links)
    await expect(page.getByRole('link', { name: /apply/i }).first()).toBeVisible()

    // The published candidate form must match the builder configuration.
    await page.goto(`/jobs/${jobSlug}/apply`)
    await expect(page.getByLabel('Cover Letter')).toBeVisible()
    await expect(page.getByText('Resume / CV', { exact: false })).toHaveCount(0)
    const publishedQuestion = page.getByLabel(UPDATED_QUESTION_LABEL)
    await expect(publishedQuestion).toBeVisible()
    await expect(publishedQuestion.getByRole('option', { name: 'Playwright' })).toHaveCount(1)
    await expect(publishedQuestion.getByRole('option', { name: 'Cypress' })).toHaveCount(1)
  })
})
