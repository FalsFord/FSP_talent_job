import { and, eq, inArray } from 'drizzle-orm'
import * as schema from '../../database/schema'
import { assertDemoAccountCanUseOrg, getDemoAccountOrgIds, isDemoAccountEmail } from '../../utils/demoOrg'

type AuthSession = NonNullable<Awaited<ReturnType<typeof auth.api.getSession>>>

const AUTH_PATH_PREFIX = '/api/auth'

function getAuthPath(pathname: string): string {
  return pathname.startsWith(AUTH_PATH_PREFIX)
    ? pathname.slice(AUTH_PATH_PREFIX.length) || '/'
    : pathname
}

function isDemoOrganizationMutation(authPath: string, method: string): boolean {
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return false
  if (!authPath.startsWith('/organization/')) return false
  return authPath !== '/organization/set-active'
}

async function findDemoMembershipOrgId(session: AuthSession): Promise<string | null> {
  const demoOrgIds = await getDemoAccountOrgIds()
  if (demoOrgIds.size === 0) return null

  const [demoMembership] = await db
    .select({ organizationId: schema.member.organizationId })
    .from(schema.member)
    .where(and(
      eq(schema.member.userId, session.user.id),
      inArray(schema.member.organizationId, [...demoOrgIds]),
    ))
    .limit(1)

  return demoMembership?.organizationId ?? null
}

async function normalizeDemoActiveOrganization(session: AuthSession): Promise<AuthSession> {
  if (!isDemoAccountEmail(session.user.email)) return session

  const activeOrganizationId = (session.session as { activeOrganizationId?: string }).activeOrganizationId
  const demoOrgIds = await getDemoAccountOrgIds()
  if (activeOrganizationId && demoOrgIds.has(activeOrganizationId)) return session

  const demoOrgId = await findDemoMembershipOrgId(session)
  if (!demoOrgId) return session

  await db
    .update(schema.session)
    .set({
      activeOrganizationId: demoOrgId,
      updatedAt: new Date(),
    })
    .where(eq(schema.session.id, session.session.id))

  return {
    ...session,
    session: {
      ...session.session,
      activeOrganizationId: demoOrgId,
    },
  } as AuthSession
}

async function resolveRequestedOrganizationId(body: unknown): Promise<string | null> {
  if (!body || typeof body !== 'object') return null

  const input = body as { organizationId?: unknown; organizationSlug?: unknown }
  if (typeof input.organizationId === 'string' && input.organizationId) {
    return input.organizationId
  }

  if (typeof input.organizationSlug === 'string' && input.organizationSlug) {
    const [org] = await db
      .select({ id: schema.organization.id })
      .from(schema.organization)
      .where(eq(schema.organization.slug, input.organizationSlug))
      .limit(1)
    return org?.id ?? null
  }

  return null
}

async function enforceDemoOrganizationAuthRequest(
  event: Parameters<typeof getRequestURL>[0],
  authPath: string,
  session: AuthSession | null,
): Promise<void> {
  if (!session || !isDemoAccountEmail(session.user.email)) return

  if (isDemoOrganizationMutation(authPath, event.method)) {
    throw createError({
      statusCode: 403,
      statusMessage: 'The demo account cannot modify organization memberships or settings.',
    })
  }

  if (authPath !== '/organization/set-active' || event.method !== 'POST') return

  const body = await readBody(event).catch(() => null)
  const targetOrgId = await resolveRequestedOrganizationId(body)
  await assertDemoAccountCanUseOrg(session.user.email, targetOrgId)
}

async function filterDemoOrganizationResponse(
  response: Response,
  authPath: string,
  session: AuthSession | null,
): Promise<Response> {
  if (!session || !isDemoAccountEmail(session.user.email)) return response
  if (authPath !== '/organization/list' || !response.ok) return response

  const body = await response.clone().json().catch(() => null)
  if (!Array.isArray(body)) return response

  const demoOrgIds = await getDemoAccountOrgIds()
  const filtered = body.filter((org: unknown) => {
    return Boolean(
      org
      && typeof org === 'object'
      && demoOrgIds.has((org as { id?: string }).id ?? ''),
    )
  })

  const headers = new Headers(response.headers)
  headers.delete('content-length')
  headers.set('content-type', 'application/json')

  return new Response(JSON.stringify(filtered), {
    status: response.status,
    statusText: response.statusText,
    headers,
  })
}

export default defineEventHandler(async (event) => {
  const requestUrl = getRequestURL(event)
  const authPath = getAuthPath(requestUrl.pathname)

  try {
    const rawSession = await auth.api.getSession({ headers: event.headers })
    const session = rawSession ? await normalizeDemoActiveOrganization(rawSession) : null

    await enforceDemoOrganizationAuthRequest(event, authPath, session)

    const response = await auth.handler(toWebRequest(event))
    return await filterDemoOrganizationResponse(response, authPath, session)
  } catch (error) {
    if (error && typeof error === 'object' && 'statusCode' in error) {
      throw error
    }

    logError('auth.handler_error', {
      http_method: event.method,
      http_path: requestUrl.pathname,
      error_message: error instanceof Error ? error.message : 'Unknown error',
    })

    // Detect BETTER_AUTH_URL mismatch — the #1 self-hosting setup issue
    const requestOrigin = requestUrl.origin
    const configuredUrl = env.BETTER_AUTH_URL?.trim() || env.RAILWAY_PUBLIC_DOMAIN?.trim()
    const configuredOrigin = configuredUrl
      ? (() => { try { return new URL(configuredUrl.startsWith('http') ? configuredUrl : `https://${configuredUrl}`).origin } catch { return configuredUrl } })()
      : undefined
    const isUrlMismatch = configuredOrigin && requestOrigin !== configuredOrigin

    if (isUrlMismatch) {
      logError('auth.url_mismatch', {
        configured_origin: configuredOrigin,
        request_origin: requestOrigin,
      })
      throw createError({
        statusCode: 500,
        statusMessage: 'Auth configuration error',
        data: {
          code: 'AUTH_URL_MISMATCH',
          message: `BETTER_AUTH_URL is set to "${configuredOrigin}" but this request came from "${requestOrigin}". `
            + 'Update the BETTER_AUTH_URL environment variable to match your deployment domain, then redeploy.',
        },
      })
    }

    const exposeDetails = isRailwayPreviewEnvironment(env.RAILWAY_ENVIRONMENT_NAME) || import.meta.dev
    const details = error instanceof Error ? error.message : 'Unknown error'

    throw createError({
      statusCode: 500,
      statusMessage: 'Server Error',
      data: {
        code: 'AUTH_HANDLER_ERROR',
        message: exposeDetails
          ? details
          : 'Authentication failed. If you are self-hosting, verify that the BETTER_AUTH_URL environment variable matches your deployment domain (e.g. "https://your-app.up.railway.app") and redeploy.',
      },
    })
  }
})
