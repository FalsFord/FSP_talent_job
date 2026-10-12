import type { MaybeRefOrGetter, Ref } from 'vue'
import type {
  PropertyDefinition,
  PropertyEntityType,
  PropertyEntry,
  PropertyType,
  PropertyConfig,
  PropertyFilter,
} from '~~/shared/properties'

/**
 * useProperties — manages the property *schema* (definitions) for a given context.
 *
 * `entityType` + optional `jobId` defines the scope:
 *   - candidate            → org-global candidate defs
 *   - application          → org-global application defs
 *   - application + jobId  → org-global + per-job (additive)
 */
export function useProperties(opts: {
  entityType: MaybeRefOrGetter<PropertyEntityType>
  jobId?: MaybeRefOrGetter<string | null | undefined>
  /** When true, only fetch per-job props (used by the per-job schema editor). */
  jobOnly?: MaybeRefOrGetter<boolean>
}) {
  const query = computed(() => {
    const entityType = toValue(opts.entityType)
    const jobId = opts.jobId ? toValue(opts.jobId) : null
    const jobOnly = opts.jobOnly ? toValue(opts.jobOnly) : false
    return {
      entityType,
      ...(jobId ? { jobId } : {}),
      ...(jobOnly ? { jobOnly: '1' } : {}),
    }
  })

  const key = computed(() => {
    const q = query.value
    return `properties-${q.entityType}-${q.jobId ?? 'org'}-${q.jobOnly ?? '0'}`
  })

  const { data, status, error, refresh } = useFetch<PropertyDefinition[]>('/api/properties', {
    key,
    query,
    headers: useRequestHeaders(['cookie']),
    default: () => [],
  })

  const definitions = computed<PropertyDefinition[]>(() => data.value ?? [])

  async function createDefinition(payload: {
    entityType: PropertyEntityType
    type: PropertyType
    name: string
    description?: string | null
    jobId?: string | null
    config?: PropertyConfig
  }) {
    const created = await $fetch<PropertyDefinition>('/api/properties', {
      method: 'POST',
      body: payload,
    })
    await refresh()
    return created
  }

  async function updateDefinition(
    id: string,
    payload: Partial<Pick<PropertyDefinition, 'name' | 'description' | 'config' | 'displayOrder'>>,
  ) {
    const updated = await $fetch<PropertyDefinition>(`/api/properties/${id}`, {
      method: 'PATCH',
      body: payload,
    })
    await refresh()
    return updated
  }

  async function deleteDefinition(id: string) {
    await $fetch(`/api/properties/${id}`, { method: 'DELETE' })
    await refresh()
  }

  async function reorderDefinitions(ids: string[]) {
    await $fetch('/api/properties/reorder', {
      method: 'POST',
      body: { ids },
    })
    await refresh()
  }

  return {
    definitions,
    status,
    error,
    refresh,
    createDefinition,
    updateDefinition,
    deleteDefinition,
    reorderDefinitions,
  }
}

/**
 * useEntityPropertyMutations — write helpers for setting/clearing values on
 * a candidate or application. Returns optimistic-friendly setters.
 */
export function useEntityPropertyMutations(opts: {
  entityType: PropertyEntityType
  entityId: MaybeRefOrGetter<string>
  /** Caller's local entries ref (for optimistic updates). */
  entries: Ref<PropertyEntry[]>
  /** Refresh callback after mutation completes successfully. */
  onAfter?: () => void | Promise<void>
}) {
  const base = computed(
    () => `/api/${opts.entityType === 'application' ? 'applications' : 'candidates'}/${toValue(opts.entityId)}/properties`,
  )

  async function setValue(propertyDefinitionId: string, value: unknown) {
    // Optimistic update
    const idx = opts.entries.value.findIndex((e) => e.definition.id === propertyDefinitionId)
    const previous = idx >= 0 ? opts.entries.value[idx]!.value : null
    if (idx >= 0) {
      opts.entries.value = opts.entries.value.map((e, i) =>
        i === idx ? { ...e, value } : e,
      )
    }

    try {
      const result = await $fetch<{ value: unknown }>(`${base.value}/${propertyDefinitionId}`, {
        method: 'PUT',
        body: { value },
      })
      // Reconcile with server response
      if (idx >= 0) {
        opts.entries.value = opts.entries.value.map((e, i) =>
          i === idx ? { ...e, value: result.value } : e,
        )
      }
      if (opts.onAfter) await opts.onAfter()
      return result.value
    } catch (err) {
      // Rollback
      if (idx >= 0) {
        opts.entries.value = opts.entries.value.map((e, i) =>
          i === idx ? { ...e, value: previous } : e,
        )
      }
      throw err
    }
  }

  async function clearValue(propertyDefinitionId: string) {
    return setValue(propertyDefinitionId, null)
  }

  return { setValue, clearValue }
}

export type { PropertyDefinition, PropertyEntry, PropertyType, PropertyEntityType, PropertyFilter }
