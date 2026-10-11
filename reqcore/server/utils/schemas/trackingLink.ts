import { z } from 'zod'

// ─────────────────────────────────────────────
// Source tracking validation schemas
// ─────────────────────────────────────────────

export const sourceChannels = [
  'linkedin', 'indeed', 'glassdoor', 'ziprecruiter', 'monster',
  'handshake', 'angellist', 'wellfound', 'dice', 'stackoverflow',
  'weworkremotely', 'remoteok', 'builtin', 'hired', 'lever',
  'greenhouse_board', 'google_jobs', 'facebook', 'twitter', 'instagram',
  'tiktok', 'reddit', 'referral', 'career_site', 'email',
  'event', 'agency', 'direct', 'other', 'custom',
] as const

export type SourceChannel = typeof sourceChannels[number]

const sourceChannelSchema = z.enum(sourceChannels)

/** Schema for creating a tracking link */
export const createTrackingLinkSchema = z.object({
  jobId: z.string().min(1).optional(),
  channel: sourceChannelSchema.default('custom'),
  name: z.string().min(1, 'Name is required').max(200),
  utmSource: z.string().max(200).optional(),
  utmMedium: z.string().max(200).optional(),
  utmCampaign: z.string().max(200).optional(),
  utmTerm: z.string().max(200).optional(),
  utmContent: z.string().max(200).optional(),
})

/** Schema for updating a tracking link */
export const updateTrackingLinkSchema = z.object({
  name: z.string().min(1).max(200).optional(),
  channel: sourceChannelSchema.optional(),
  utmSource: z.string().max(200).optional(),
  utmMedium: z.string().max(200).optional(),
  utmCampaign: z.string().max(200).optional(),
  utmTerm: z.string().max(200).optional(),
  utmContent: z.string().max(200).optional(),
  isActive: z.boolean().optional(),
})

/** Route param for tracking link ID */
export const trackingLinkIdSchema = z.object({
  id: z.string().min(1),
})

/** Query params for listing tracking links */
export const trackingLinkQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(50),
  jobId: z.string().min(1).optional(),
  channel: sourceChannelSchema.optional(),
  isActive: z.enum(['true', 'false']).optional().transform((v) => v === undefined ? undefined : v === 'true'),
})

/** Query params for source tracking stats */
export const sourceStatsQuerySchema = z.object({
  jobId: z.string().min(1).optional(),
  from: z.string().datetime().optional(),
  to: z.string().datetime().optional(),
})

/**
 * Schema added to the public application to capture source attribution.
 * These fields are appended by the client from URL query parameters.
 */
export const applicationSourceSchema = z.object({
  ref: z.string().max(100).optional(),
  utmSource: z.string().max(200).optional(),
  utmMedium: z.string().max(200).optional(),
  utmCampaign: z.string().max(200).optional(),
  utmTerm: z.string().max(200).optional(),
  utmContent: z.string().max(200).optional(),
})
