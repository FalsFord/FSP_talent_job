import { eq } from 'drizzle-orm'
import { interview, application, organization } from '../../../database/schema'
import { verifyInterviewToken } from '../../../utils/interview-token'

/**
 * GET /api/public/interviews/respond?token=xxx
 *
 * Public endpoint for candidates to preview an interview invitation before responding.
 * Returns interview details + the action encoded in the HMAC-signed token.
 * No authentication required — the token is the proof of authorization.
 */
export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const token = typeof query.token === 'string' ? query.token : ''

  if (!token) {
    throw createError({ statusCode: 400, statusMessage: 'Missing token' })
  }

  const payload = verifyInterviewToken(token, env.BETTER_AUTH_SECRET)
  if (!payload) {
    throw createError({ statusCode: 400, statusMessage: 'Invalid or expired token' })
  }

  const interviewRecord = await db.query.interview.findFirst({
    where: eq(interview.id, payload.id),
  })

  if (!interviewRecord) {
    throw createError({ statusCode: 404, statusMessage: 'Interview not found' })
  }

  // Fetch related data for display
  const app = await db.query.application.findFirst({
    where: eq(application.id, interviewRecord.applicationId),
    with: {
      candidate: { columns: { firstName: true, lastName: true, email: true } },
      job: { columns: { title: true } },
    },
  })

  const org = await db.query.organization.findFirst({
    where: eq(organization.id, interviewRecord.organizationId),
    columns: { name: true },
  })

  return {
    action: payload.action,
    interview: {
      id: interviewRecord.id,
      title: interviewRecord.title,
      type: interviewRecord.type,
      status: interviewRecord.status,
      scheduledAt: interviewRecord.scheduledAt,
      duration: interviewRecord.duration,
      location: interviewRecord.location,
      candidateResponse: interviewRecord.candidateResponse,
    },
    candidate: app?.candidate
      ? {
          firstName: app.candidate.firstName,
          lastName: app.candidate.lastName,
        }
      : null,
    jobTitle: app?.job?.title ?? null,
    organizationName: org?.name ?? null,
  }
})
