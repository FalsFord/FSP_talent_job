import { eq } from 'drizzle-orm'
import { z } from 'zod'
import { interview } from '../../../database/schema'
import { verifyInterviewToken } from '../../../utils/interview-token'

const respondBodySchema = z.object({
  token: z.string().min(1, 'Token is required'),
})

/**
 * POST /api/public/interviews/respond  { token: "xxx" }
 *
 * Public endpoint for candidates to confirm their interview response.
 * Updates candidateResponse + candidateRespondedAt in the database.
 * No authentication required — the HMAC-signed token is the proof of authorization.
 */
export default defineEventHandler(async (event) => {
  const body = await readValidatedBody(event, respondBodySchema.parse)
  const token = body.token

  const payload = verifyInterviewToken(token, env.BETTER_AUTH_SECRET)
  if (!payload) {
    throw createError({ statusCode: 400, statusMessage: 'Invalid or expired token' })
  }

  // Fetch the interview to verify it still exists and is in a respondable state
  const interviewRecord = await db.query.interview.findFirst({
    where: eq(interview.id, payload.id),
  })

  if (!interviewRecord) {
    throw createError({ statusCode: 404, statusMessage: 'Interview not found' })
  }

  if (interviewRecord.status !== 'scheduled') {
    throw createError({
      statusCode: 400,
      statusMessage: `This interview has been ${interviewRecord.status} and can no longer be responded to.`,
    })
  }

  // Idempotency: if already responded with the same action, return early
  if (interviewRecord.candidateResponse === payload.action) {
    return {
      success: true,
      interviewId: interviewRecord.id,
      response: interviewRecord.candidateResponse,
      respondedAt: interviewRecord.candidateRespondedAt,
    }
  }

  // Update the candidate's response
  const [updated] = await db.update(interview)
    .set({
      candidateResponse: payload.action,
      candidateRespondedAt: new Date(),
      updatedAt: new Date(),
    })
    .where(eq(interview.id, payload.id))
    .returning({
      id: interview.id,
      candidateResponse: interview.candidateResponse,
      candidateRespondedAt: interview.candidateRespondedAt,
    })

  return {
    success: true,
    interviewId: updated?.id,
    response: updated?.candidateResponse,
    respondedAt: updated?.candidateRespondedAt,
  }
})
