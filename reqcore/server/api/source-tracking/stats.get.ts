import { eq, and, sql, count, gte, lte, desc } from 'drizzle-orm'
import { applicationSource, application, trackingLink, job, candidate } from '../../database/schema'
import { sourceStatsQuerySchema } from '../../utils/schemas/trackingLink'

/**
 * GET /api/source-tracking/stats
 * Returns comprehensive source analytics for the current organization:
 * - Channel breakdown (applications per source channel)
 * - Top tracking links by applications
 * - Source trends over time (last 30 days by default)
 * - Conversion funnel (applications by status per channel)
 * - Recent attributed applications
 */
export default defineEventHandler(async (event) => {
  const session = await requirePermission(event, { sourceTracking: ['read'], application: ['read'] })
  const orgId = session.session.activeOrganizationId

  const query = await getValidatedQuery(event, sourceStatsQuerySchema.parse)

  // Build date range conditions
  const dateConditions = [eq(applicationSource.organizationId, orgId)]
  if (query.jobId) {
    dateConditions.push(eq(application.jobId, query.jobId))
  }
  if (query.from) {
    dateConditions.push(gte(applicationSource.createdAt, new Date(query.from)))
  }
  if (query.to) {
    dateConditions.push(lte(applicationSource.createdAt, new Date(query.to)))
  }

  const whereClause = and(...dateConditions)

  // ─────────────────────────────────────────────
  // Run all analytics queries in parallel
  // ─────────────────────────────────────────────
  const [
    channelBreakdown,
    topLinks,
    statusByChannel,
    dailyTrend,
    recentAttributed,
    totalTracked,
    totalUntracked,
    topReferrerDomains,
  ] = await Promise.all([
    // 1. Applications per channel
    db
      .select({
        channel: applicationSource.channel,
        count: count().as('count'),
      })
      .from(applicationSource)
      .innerJoin(application, eq(application.id, applicationSource.applicationId))
      .where(whereClause)
      .groupBy(applicationSource.channel)
      .orderBy(sql`count(*) desc`),

    // 2. Top 10 tracking links by application count
    db
      .select({
        id: trackingLink.id,
        name: trackingLink.name,
        channel: trackingLink.channel,
        code: trackingLink.code,
        jobTitle: job.title,
        clickCount: trackingLink.clickCount,
        applicationCount: trackingLink.applicationCount,
        isActive: trackingLink.isActive,
      })
      .from(trackingLink)
      .leftJoin(job, eq(job.id, trackingLink.jobId))
      .where(eq(trackingLink.organizationId, orgId))
      .orderBy(desc(trackingLink.applicationCount))
      .limit(10),

    // 3. Conversion funnel — application status breakdown per channel
    db
      .select({
        channel: applicationSource.channel,
        status: application.status,
        count: count().as('count'),
      })
      .from(applicationSource)
      .innerJoin(application, eq(application.id, applicationSource.applicationId))
      .where(whereClause)
      .groupBy(applicationSource.channel, application.status),

    // 4. Daily trend for the last 30 days
    db
      .select({
        date: sql<string>`date_trunc('day', ${applicationSource.createdAt})::date`.as('day'),
        channel: applicationSource.channel,
        count: count().as('count'),
      })
      .from(applicationSource)
      .innerJoin(application, eq(application.id, applicationSource.applicationId))
      .where(and(
        ...dateConditions,
        gte(applicationSource.createdAt, sql`now() - interval '30 days'`),
      ))
      .groupBy(sql`date_trunc('day', ${applicationSource.createdAt})::date`, applicationSource.channel)
      .orderBy(sql`date_trunc('day', ${applicationSource.createdAt})::date`),

    // 5. Recent 15 attributed applications with candidate + job info
    db
      .select({
        applicationId: applicationSource.applicationId,
        jobId: application.jobId,
        channel: applicationSource.channel,
        utmSource: applicationSource.utmSource,
        utmCampaign: applicationSource.utmCampaign,
        referrerDomain: applicationSource.referrerDomain,
        trackingLinkName: trackingLink.name,
        candidateFirstName: candidate.firstName,
        candidateLastName: candidate.lastName,
        candidateEmail: candidate.email,
        jobTitle: job.title,
        status: application.status,
        appliedAt: applicationSource.createdAt,
      })
      .from(applicationSource)
      .innerJoin(application, eq(application.id, applicationSource.applicationId))
      .innerJoin(candidate, eq(candidate.id, application.candidateId))
      .innerJoin(job, eq(job.id, application.jobId))
      .leftJoin(trackingLink, eq(trackingLink.id, applicationSource.trackingLinkId))
      .where(whereClause)
      .orderBy(desc(applicationSource.createdAt))
      .limit(200),

    // 6. Total tracked applications (have a source)
    db.$count(applicationSource, eq(applicationSource.organizationId, orgId)),

    // 7. Total untracked applications (no source record)
    db.execute(sql`
      SELECT count(*) as count
      FROM ${application} a
      WHERE a.organization_id = ${orgId}
        AND NOT EXISTS (
          SELECT 1 FROM ${applicationSource} s
          WHERE s.application_id = a.id
        )
    `).then((r: any) => Number(r[0]?.count ?? 0)),

    // 8. Top referrer domains
    db
      .select({
        domain: applicationSource.referrerDomain,
        count: count().as('count'),
      })
      .from(applicationSource)
      .innerJoin(application, eq(application.id, applicationSource.applicationId))
      .where(and(
        ...dateConditions,
        sql`${applicationSource.referrerDomain} IS NOT NULL`,
      ))
      .groupBy(applicationSource.referrerDomain)
      .orderBy(sql`count(*) desc`)
      .limit(10),
  ])

  // ─────────────────────────────────────────────
  // Build conversion funnel map: channel → status → count
  // ─────────────────────────────────────────────
  const funnel: Record<string, Record<string, number>> = {}
  for (const row of statusByChannel) {
    if (!funnel[row.channel]) {
      funnel[row.channel] = { new: 0, screening: 0, interview: 0, offer: 0, hired: 0, rejected: 0 }
    }
    funnel[row.channel]![row.status] = row.count
  }

  return {
    channelBreakdown,
    topLinks,
    funnel,
    dailyTrend,
    recentAttributed,
    topReferrerDomains,
    summary: {
      totalTracked,
      totalUntracked,
      attributionRate: totalTracked + totalUntracked > 0
        ? Math.round((totalTracked / (totalTracked + totalUntracked)) * 100)
        : 0,
    },
  }
})
