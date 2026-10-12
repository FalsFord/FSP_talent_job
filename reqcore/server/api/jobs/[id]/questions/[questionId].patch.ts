import { eq, and } from 'drizzle-orm'
import { jobQuestion } from '../../../../database/schema'
import { questionIdParamSchema, questionStateSchema, updateQuestionSchema } from '../../../../utils/schemas/jobQuestion'

export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { job: ['update'] })
  const orgId = session.session.activeOrganizationId

  const { id: jobId, questionId } = await getValidatedRouterParams(event, questionIdParamSchema.parse)
  const body = await readValidatedBody(event, updateQuestionSchema.parse)

  const existing = await db.query.jobQuestion.findFirst({
    where: and(
      eq(jobQuestion.id, questionId),
      eq(jobQuestion.jobId, jobId),
      eq(jobQuestion.organizationId, orgId),
    ),
    columns: {
      type: true,
      options: true,
    },
  })

  if (!existing) {
    throw createError({ statusCode: 404, statusMessage: 'Question not found' })
  }

  const mergedState = questionStateSchema.safeParse({
    type: body.type ?? existing.type,
    options: body.options === undefined ? existing.options : body.options,
  })
  if (!mergedState.success) {
    throw createError({
      statusCode: 400,
      statusMessage: mergedState.error.issues[0]?.message ?? 'Invalid question',
    })
  }

  const [updated] = await db.update(jobQuestion)
    .set({
      ...body,
      updatedAt: new Date(),
    })
    .where(and(
      eq(jobQuestion.id, questionId),
      eq(jobQuestion.jobId, jobId),
      eq(jobQuestion.organizationId, orgId),
    ))
    .returning({
      id: jobQuestion.id,
      jobId: jobQuestion.jobId,
      type: jobQuestion.type,
      label: jobQuestion.label,
      description: jobQuestion.description,
      required: jobQuestion.required,
      options: jobQuestion.options,
      displayOrder: jobQuestion.displayOrder,
      createdAt: jobQuestion.createdAt,
      updatedAt: jobQuestion.updatedAt,
    })

  if (!updated) {
    throw createError({ statusCode: 404, statusMessage: 'Question not found' })
  }

  return updated
})
