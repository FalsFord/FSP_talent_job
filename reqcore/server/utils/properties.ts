import { and, eq, inArray, isNull, or, sql } from 'drizzle-orm'
import { propertyDefinition, propertyValue } from '../database/schema'
import type { PropertyEntityType, PropertyType } from './schemas/property'

// ─────────────────────────────────────────────
// Property loading & attachment helpers
// ─────────────────────────────────────────────

export type PropertyDefinitionRow = {
  id: string
  organizationId: string
  jobId: string | null
  entityType: PropertyEntityType
  type: PropertyType
  name: string
  description: string | null
  displayOrder: number
  config: Record<string, unknown> | null
  createdAt: Date
  updatedAt: Date
}

export type PropertyEntry = {
  definition: PropertyDefinitionRow
  value: unknown
}

/**
 * Load all property definitions visible in a given context.
 *  - Candidate context: org-global candidate definitions only.
 *  - Application context: org-global application defs + per-job defs for jobId (additive).
 *
 * Ordered by (jobId NULLS FIRST, displayOrder, createdAt) so org-global props
 * always render first.
 */
export async function loadPropertyDefinitions(opts: {
  organizationId: string
  entityType: PropertyEntityType
  jobId?: string | null
}): Promise<PropertyDefinitionRow[]> {
  const { organizationId, entityType, jobId } = opts

  const where =
    entityType === 'candidate'
      ? and(
          eq(propertyDefinition.organizationId, organizationId),
          eq(propertyDefinition.entityType, 'candidate'),
          isNull(propertyDefinition.jobId),
        )
      : and(
          eq(propertyDefinition.organizationId, organizationId),
          eq(propertyDefinition.entityType, 'application'),
          jobId
            ? or(isNull(propertyDefinition.jobId), eq(propertyDefinition.jobId, jobId))
            : isNull(propertyDefinition.jobId),
        )

  const rows = await db
    .select()
    .from(propertyDefinition)
    .where(where)
    .orderBy(
      sql`${propertyDefinition.jobId} NULLS FIRST`,
      propertyDefinition.displayOrder,
      propertyDefinition.createdAt,
    )

  return rows as unknown as PropertyDefinitionRow[]
}

/**
 * Load values for a single entity, returning [{ definition, value }] entries
 * in the same order as definitions (missing values surface as `value: null`).
 */
export async function loadPropertyEntriesForEntity(opts: {
  organizationId: string
  entityType: PropertyEntityType
  entityId: string
  jobId?: string | null
}): Promise<PropertyEntry[]> {
  const definitions = await loadPropertyDefinitions(opts)
  if (definitions.length === 0) return []

  const values = await db
    .select({
      propertyDefinitionId: propertyValue.propertyDefinitionId,
      value: propertyValue.value,
    })
    .from(propertyValue)
    .where(
      and(
        eq(propertyValue.organizationId, opts.organizationId),
        eq(propertyValue.entityType, opts.entityType),
        eq(propertyValue.entityId, opts.entityId),
        inArray(
          propertyValue.propertyDefinitionId,
          definitions.map((d) => d.id),
        ),
      ),
    )

  const valueMap = new Map(values.map((v) => [v.propertyDefinitionId, v.value]))
  return definitions.map((definition) => ({
    definition,
    value: valueMap.get(definition.id) ?? null,
  }))
}

/**
 * Bulk load values for many entities. Returns a Map<entityId, PropertyEntry[]>
 * suitable for splicing into list endpoint responses.
 */
export async function loadPropertyEntriesForEntities(opts: {
  organizationId: string
  entityType: PropertyEntityType
  entityIds: string[]
  /**
   * For application list responses we may want per-job props too. The
   * caller passes the union of jobIds; we then load all defs whose jobId
   * is null OR in that set.
   */
  jobIds?: string[]
  /**
   * Optional per-entity job-id map. When provided, each entity only
   * receives org-global defs plus defs scoped to that entity's own jobId,
   * so mixed-job lists don't leak unrelated job properties across rows.
   */
  entityJobIds?: Map<string, string | null | undefined>
}): Promise<Map<string, PropertyEntry[]>> {
  const { organizationId, entityType, entityIds, jobIds, entityJobIds } = opts
  if (entityIds.length === 0) return new Map()

  const where =
    entityType === 'candidate'
      ? and(
          eq(propertyDefinition.organizationId, organizationId),
          eq(propertyDefinition.entityType, 'candidate'),
          isNull(propertyDefinition.jobId),
        )
      : and(
          eq(propertyDefinition.organizationId, organizationId),
          eq(propertyDefinition.entityType, 'application'),
          jobIds && jobIds.length > 0
            ? or(isNull(propertyDefinition.jobId), inArray(propertyDefinition.jobId, jobIds))
            : isNull(propertyDefinition.jobId),
        )

  const definitions = (await db
    .select()
    .from(propertyDefinition)
    .where(where)
    .orderBy(
      sql`${propertyDefinition.jobId} NULLS FIRST`,
      propertyDefinition.displayOrder,
      propertyDefinition.createdAt,
    )) as unknown as PropertyDefinitionRow[]

  if (definitions.length === 0) return new Map(entityIds.map((id) => [id, []]))

  const values = await db
    .select({
      propertyDefinitionId: propertyValue.propertyDefinitionId,
      entityId: propertyValue.entityId,
      value: propertyValue.value,
    })
    .from(propertyValue)
    .where(
      and(
        eq(propertyValue.organizationId, organizationId),
        eq(propertyValue.entityType, entityType),
        inArray(propertyValue.entityId, entityIds),
        inArray(
          propertyValue.propertyDefinitionId,
          definitions.map((d) => d.id),
        ),
      ),
    )

  const map = new Map<string, PropertyEntry[]>()
  for (const id of entityIds) map.set(id, [])

  // Build a per-entity value lookup
  const byEntity = new Map<string, Map<string, unknown>>()
  for (const v of values) {
    let perEntity = byEntity.get(v.entityId)
    if (!perEntity) {
      perEntity = new Map()
      byEntity.set(v.entityId, perEntity)
    }
    perEntity.set(v.propertyDefinitionId, v.value)
  }

  for (const entityId of entityIds) {
    const list = map.get(entityId)!
    const perEntity = byEntity.get(entityId)
    const ownJobId = entityJobIds?.get(entityId) ?? null
    for (const def of definitions) {
      // Each entity sees org-global defs (jobId === null) plus only the
      // defs bound to its own jobId. When the caller doesn't pass
      // entityJobIds, fall back to legacy behavior (include all loaded defs).
      if (entityJobIds && def.jobId !== null && def.jobId !== ownJobId) continue
      list.push({ definition: def, value: perEntity?.get(def.id) ?? null })
    }
  }

  return map
}

/**
 * Find the entity ids matching a set of property filters (AND across filters).
 * Each filter is { propertyDefinitionId, op, value }.
 *  - op='equals' for select, checkbox, text-equals, number-equals
 *  - op='contains' for text/long_text/url/email substring match
 *  - op='in' for multi_select (any-of)
 *  - op='isEmpty' / 'isNotEmpty' for null checks
 *
 * Returns a Set<entityId>. Caller intersects with their other WHERE conditions.
 */
export type PropertyFilter = {
  propertyDefinitionId: string
  op: 'equals' | 'contains' | 'in' | 'isEmpty' | 'isNotEmpty'
  value?: unknown
}

export async function entityIdsMatchingFilters(opts: {
  organizationId: string
  entityType: PropertyEntityType
  filters: PropertyFilter[]
}): Promise<Set<string> | null> {
  const { organizationId, entityType, filters } = opts
  if (filters.length === 0) return null

  // Each filter narrows the candidate set; intersect.
  let working: Set<string> | null = null

  for (const f of filters) {
    const baseWhere = and(
      eq(propertyValue.organizationId, organizationId),
      eq(propertyValue.entityType, entityType),
      eq(propertyValue.propertyDefinitionId, f.propertyDefinitionId),
    )

    let matchingRows: { entityId: string }[] = []

    if (f.op === 'isEmpty') {
      // Computing the complement requires a universe of entity ids that this
      // helper doesn't have. Reject the operator at the API boundary instead
      // of silently collapsing the match set to empty.
      throw createError({
        statusCode: 400,
        statusMessage: "Filter operator 'isEmpty' is not supported in list queries",
      })
    }

    if (f.op === 'isNotEmpty') {
      matchingRows = await db
        .select({ entityId: propertyValue.entityId })
        .from(propertyValue)
        .where(and(baseWhere, sql`${propertyValue.value} IS NOT NULL`))
    }
    else if (f.op === 'equals') {
      matchingRows = await db
        .select({ entityId: propertyValue.entityId })
        .from(propertyValue)
        .where(and(baseWhere, sql`${propertyValue.value} = ${JSON.stringify(f.value)}::jsonb`))
    }
    else if (f.op === 'contains') {
      const needle = String(f.value ?? '').toLowerCase()
      matchingRows = await db
        .select({ entityId: propertyValue.entityId })
        .from(propertyValue)
        .where(
          and(
            baseWhere,
            sql`lower(${propertyValue.value}::text) LIKE ${'%' + needle.replace(/[%_\\]/g, '\\$&') + '%'}`,
          ),
        )
    }
    else if (f.op === 'in') {
      const needles = Array.isArray(f.value) ? f.value.map(String) : []
      if (needles.length === 0) {
        working = new Set()
        break
      }
      // Match where the jsonb value array contains any of the needles
      matchingRows = await db
        .select({ entityId: propertyValue.entityId })
        .from(propertyValue)
        .where(
          and(
            baseWhere,
            sql`${propertyValue.value} ?| ${needles}::text[]`,
          ),
        )
    }

    const next = new Set(matchingRows.map((r) => r.entityId))
    if (working === null) {
      working = next
    } else {
      // intersect
      const intersected = new Set<string>()
      for (const id of working) if (next.has(id)) intersected.add(id)
      working = intersected
    }
    if (working.size === 0) break
  }

  return working
}
