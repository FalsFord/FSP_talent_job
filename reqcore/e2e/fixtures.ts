import { test as base, type BrowserContext, type Page } from '@playwright/test'

/**
 * Shared test fixtures for Reqcore E2E tests.
 *
 * Provides a unique test account per worker so parallel runs
 * won't clash (currently single-worker, but future-proofed).
 */

export interface TestAccount {
  name: string
  email: string
  password: string
  orgName: string
  orgSlug: string
}

function generateTestAccount(workerId: number): TestAccount {
  const id = `${Date.now()}-${workerId}`
  return {
    name: `E2E Tester ${id}`,
    email: `e2e-${id}@test.local`,
    password: process.env.E2E_TEST_PASSWORD || 'TestPassword123!',
    orgName: `E2E Org ${id}`,
    orgSlug: `e2e-org-${id}`,
  }
}

type Fixtures = {
  testAccount: TestAccount
  authenticatedPage: Page
}

export async function declineAnalyticsConsent(context: BrowserContext) {
  await context.addCookies([{
    name: 'reqcore-consent',
    value: 'denied',
    url: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3333',
  }])
}

export const test = base.extend<Fixtures>({
  testAccount: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use, workerInfo) => {
      const account = generateTestAccount(workerInfo.workerIndex)
      await use(account)
    },
    { scope: 'test' },
  ],

  authenticatedPage: async ({ page, testAccount }, use) => {
    await declineAnalyticsConsent(page.context())

    // Sign up
    await page.goto('/auth/sign-up')
    await page.waitForLoadState('networkidle')
    await page.getByLabel('Name').fill(testAccount.name)
    await page.getByLabel('Email').fill(testAccount.email)
    await page.getByLabel('Password', { exact: true }).fill(testAccount.password)
    await page.getByLabel('Confirm password').fill(testAccount.password)

    // Click sign-up and wait for the auth API response before expecting navigation
    await Promise.all([
      page.waitForResponse(
        resp => resp.url().includes('/api/auth/sign-up') && resp.status() === 200,
        { timeout: 30_000 },
      ),
      page.getByRole('button', { name: 'Sign up' }).click(),
    ])

    // After sign-up the app navigates to /onboarding/create-org, but the
    // auth middleware may not yet recognise the freshly-set session cookie
    // and redirect to /auth/sign-in instead.  Handle both outcomes.
    await page.waitForURL(
      url => url.pathname.includes('/onboarding/') || url.pathname.includes('/auth/sign-in'),
      { waitUntil: 'commit', timeout: 30_000 },
    )

    // If we landed on sign-in, explicitly sign in with the new credentials
    if (page.url().includes('/auth/sign-in')) {
      await page.waitForLoadState('networkidle')
      await page.getByLabel('Email').fill(testAccount.email)
      await page.getByLabel('Password').fill(testAccount.password)

      await Promise.all([
        page.waitForResponse(
          resp => resp.url().includes('/api/auth/sign-in') && resp.status() === 200,
          { timeout: 30_000 },
        ),
        page.getByRole('button', { name: 'Sign in', exact: true }).click(),
      ])

      // The API response confirms the session cookie is set. Navigate directly
      // instead of depending on the sign-in page's client redirect timing.
      await page.goto('/onboarding/create-org')
    }

    // Wait for the org-creation form to render (loading spinner may show first)
    await page.getByLabel('Organization name').waitFor({ state: 'visible', timeout: 30_000 })
    await page.getByLabel('Organization name').fill(testAccount.orgName)
    await page.getByRole('button', { name: 'Create organization' }).click()

    // Creating the org performs a hard navigation. Under load, the freshly
    // updated session can race that navigation and land on sign-in instead.
    await page.waitForURL(
      url => url.pathname.includes('/dashboard') || url.pathname.includes('/auth/sign-in'),
      { waitUntil: 'commit', timeout: 30_000 },
    )

    if (page.url().includes('/auth/sign-in')) {
      await page.getByLabel('Email').fill(testAccount.email)
      await page.getByLabel('Password').fill(testAccount.password)
      await Promise.all([
        page.waitForResponse(
          resp => resp.url().includes('/api/auth/sign-in') && resp.status() === 200,
          { timeout: 30_000 },
        ),
        page.getByRole('button', { name: 'Sign in', exact: true }).click(),
      ])
      await page.goto('/dashboard')
    }

    // Do not hand the page to the test while dashboard auth middleware is
    // still settling; otherwise the test's first navigation can race a
    // delayed redirect back to sign-in.
    await page.waitForLoadState('networkidle')
    if (page.url().includes('/auth/sign-in')) {
      await page.getByLabel('Email').fill(testAccount.email)
      await page.getByLabel('Password').fill(testAccount.password)
      await Promise.all([
        page.waitForResponse(
          resp => resp.url().includes('/api/auth/sign-in') && resp.status() === 200,
          { timeout: 30_000 },
        ),
        page.getByRole('button', { name: 'Sign in', exact: true }).click(),
      ])
      await page.goto('/dashboard')
      await page.waitForLoadState('networkidle')
    }

    await use(page)
  },
})

export { expect } from '@playwright/test'
