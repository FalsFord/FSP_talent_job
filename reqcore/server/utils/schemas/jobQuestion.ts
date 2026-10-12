import { z } from 'zod'

// ─────────────────────────────────────────────
// Job question validation schemas
// ─────────────────────────────────────────────

const questionTypes = ['short_text', 'long_text', 'single_select', 'multi_select', 'number', 'date', 'url', 'checkbox', 'file_upload'] as const

function validateSelectOptions(
  data: { type: typeof questionTypes[number], options?: string[] | null },
  ctx: z.RefinementCtx,
) {
  if (data.type !== 'single_select' && data.type !== 'multi_select') return

  if (!data.options?.length) {
    ctx.addIssue({
      code: 'custom',
      message: 'Options are required for select-type questions',
      path: ['options'],
    })
    return
  }

  const normalized = data.options.map(option => option.toLocaleLowerCase())
  if (new Set(normalized).size !== normalized.length) {
    ctx.addIssue({
      code: 'custom',
      message: 'Options must be unique',
      path: ['options'],
    })
  }
}

/** Schema for creating a new custom question */
export const createQuestionSchema = z.object({
  label: z.string().trim().min(1, 'Label is required').max(500),
  type: z.enum(questionTypes).default('short_text'),
  description: z.string().trim().max(1000).optional(),
  required: z.boolean().default(false),
  options: z.array(z.string().trim().min(1).max(200)).min(1).max(50).optional(),
  displayOrder: z.number().int().min(0).default(0),
}).superRefine(validateSelectOptions)

/** Schema for updating an existing question (all fields optional) */
export const updateQuestionSchema = z.object({
  label: z.string().trim().min(1).max(500).optional(),
  type: z.enum(questionTypes).optional(),
  description: z.string().trim().max(1000).nullish(),
  required: z.boolean().optional(),
  options: z.array(z.string().trim().min(1).max(200)).min(1).max(50).nullish(),
  displayOrder: z.number().int().min(0).optional(),
})

/** Validates invariants after an existing question and a partial update are merged. */
export const questionStateSchema = z.object({
  type: z.enum(questionTypes),
  options: z.array(z.string().trim().min(1).max(200)).min(1).max(50).nullish(),
}).superRefine(validateSelectOptions)

/** Schema for bulk reordering questions */
export const reorderQuestionsSchema = z.object({
  order: z.array(
    z.object({
      id: z.string().min(1),
      displayOrder: z.number().int().min(0),
    }),
  ).min(1),
})

/** Route param schema for job id */
export const jobIdParamSchema = z.object({
  id: z.string().min(1),
})

/** Route param schema for job id + questionId */
export const questionIdParamSchema = z.object({
  id: z.string().min(1),
  questionId: z.string().min(1),
})
