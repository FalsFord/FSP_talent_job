import { z } from 'zod'
import { createQuestionSchema } from './jobQuestion'
import { createCriterionSchema } from './scoring'

export { JOB_STATUS_TRANSITIONS } from '../../../shared/status-transitions'

// ─────────────────────────────────────────────
// Job validation schemas — shared across API routes
// ─────────────────────────────────────────────

/** Schema for creating a new job */
export const createJobSchema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200),
  description: z.string().trim().max(100_000).optional(),
  location: z.string().trim().max(500).optional(),
  type: z.enum(['full_time', 'part_time', 'contract', 'internship']).default('full_time'),
  /** Optional custom slug — if omitted, generated from title */
  slug: z.string().max(80).optional(),
  /** Salary range fields for SEO-rich job postings (Google Jobs) */
  salaryMin: z.coerce.number().int().min(0).nullable().optional(),
  salaryMax: z.coerce.number().int().min(0).nullable().optional(),
  salaryCurrency: z.string().length(3).nullable().optional(),
  salaryUnit: z.enum(['YEAR', 'MONTH', 'HOUR']).nullable().optional(),
  /** Whether salary is negotiable (hides min/max range on public listing) */
  salaryNegotiable: z.boolean().optional().default(false),
  /** Remote work status: remote, hybrid, or onsite */
  remoteStatus: z.enum(['remote', 'hybrid', 'onsite']).nullable().optional(),
  /** When this job listing expires (required for Google Jobs rich results) */
  validThrough: z.coerce.date().nullable().optional(),
  /** Whether the application form requires a resume/CV upload */
  requireResume: z.boolean().optional().default(false),
  /** Whether phone is hidden, optional, or required on the application form */
  phoneRequirement: z.enum(['hidden', 'optional', 'required']).optional().default('optional'),
  /** Whether the application form asks for a cover letter upload */
  requireCoverLetter: z.boolean().optional().default(false),
  /** Whether to automatically run AI scoring when a candidate applies */
  autoScoreOnApply: z.boolean().optional().default(false),
  /** Experience level required for this role */
  experienceLevel: z.enum(['junior', 'mid', 'senior', 'lead']).optional(),
})

/**
 * Atomic payload used by the create-job wizard. Keeping related records in the
 * same transaction prevents retries from leaving duplicate or partially-built
 * jobs behind.
 */
export const createJobWizardSchema = createJobSchema.extend({
  status: z.enum(['draft', 'open']).optional().default('draft'),
  questions: z.array(createQuestionSchema).max(50).optional().default([]),
  criteria: z.array(createCriterionSchema).max(20).optional().default([]),
}).superRefine((data, ctx) => {
  const criterionKeys = data.criteria.map(criterion => criterion.key)
  if (new Set(criterionKeys).size !== criterionKeys.length) {
    ctx.addIssue({
      code: 'custom',
      message: 'Scoring criterion keys must be unique',
      path: ['criteria'],
    })
  }

  if (data.autoScoreOnApply && data.criteria.length === 0) {
    ctx.addIssue({
      code: 'custom',
      message: 'At least one scoring criterion is required when automatic scoring is enabled',
      path: ['criteria'],
    })
  }
})

/** Schema for updating an existing job (all fields optional, no defaults — PATCH semantics) */
export const updateJobSchema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200).optional(),
  description: z.string().trim().max(100_000).nullable().optional(),
  location: z.string().trim().max(500).nullable().optional(),
  type: z.enum(['full_time', 'part_time', 'contract', 'internship']).optional(),
  slug: z.string().max(80).optional(),
  /** Pass null to explicitly clear a salary field */
  salaryMin: z.coerce.number().int().min(0).nullable().optional(),
  salaryMax: z.coerce.number().int().min(0).nullable().optional(),
  salaryCurrency: z.string().length(3).nullable().optional(),
  salaryUnit: z.enum(['YEAR', 'MONTH', 'HOUR']).nullable().optional(),
  salaryNegotiable: z.boolean().optional(),
  remoteStatus: z.enum(['remote', 'hybrid', 'onsite']).nullable().optional(),
  /** Pass null to explicitly clear the expiry date */
  validThrough: z.coerce.date().nullable().optional(),
  requireResume: z.boolean().optional(),
  phoneRequirement: z.enum(['hidden', 'optional', 'required']).optional(),
  requireCoverLetter: z.boolean().optional(),
  /** Whether to automatically run AI scoring when a candidate applies */
  autoScoreOnApply: z.boolean().optional(),
  /** Experience level required for this role */
  experienceLevel: z.enum(['junior', 'mid', 'senior', 'lead']).nullable().optional(),
  status: z.enum(['draft', 'open', 'closed', 'archived']).optional(),
})

/** Schema for job list query params */
export const jobQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  status: z.enum(['draft', 'open', 'closed', 'archived']).optional(),
})

/** Reusable schema for `:id` route params */
export const idParamSchema = z.object({
  id: z.string().min(1),
})

// Status transition rules are now in shared/status-transitions.ts
// and re-exported above for backward compatibility.
