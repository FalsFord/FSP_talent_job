<script setup lang="ts">
import {
  AlignLeft, Calendar, CheckSquare, CircleDot, Hash, Link as LinkIcon,
  List, Mail, Paperclip, Plus, Settings2, Text as TextIcon, User,
} from 'lucide-vue-next'
import type {
  PropertyDefinition,
  PropertyEntityType,
  PropertyEntry,
  PropertyType,
} from '~~/shared/properties'

/**
 * PropertyBlock — Notion-style properties area for an entity detail page.
 *
 * Renders one row per property: [icon] [name]  [editable value].
 * Includes "+ Add property" + "Manage properties" affordances at the bottom
 * which both open PropertySchemaEditor.
 *
 * The parent page owns the entity's property entries (via the entity GET endpoint)
 * and passes them in. This component handles UI + writes back via the API.
 */

const props = defineProps<{
  entityType: PropertyEntityType
  entityId: string
  /** Job id, only used to scope per-job application properties + the schema editor. */
  jobId?: string | null
  entries: PropertyEntry[]
  /** Optional read-only entries to render above (e.g. form question responses). */
  readOnlyEntries?: PropertyEntry[]
  /** Hide management affordances (used in dense embeds). */
  managementDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const toast = useToast()
const { handlePreviewReadOnlyError } = usePreviewReadOnly()

// Local working copy of entries so optimistic updates feel instant.
const localEntries = ref<PropertyEntry[]>(props.entries)
watch(
  () => props.entries,
  (next) => { localEntries.value = next },
  { deep: false },
)

const { setValue: persistValue } = useEntityPropertyMutations({
  entityType: props.entityType,
  entityId: () => props.entityId,
  entries: localEntries,
  // No full-page refresh needed: optimistic update + server reconciliation
  // already keeps localEntries in sync. A full refresh causes visible flicker.
})

const savingId = ref<string | null>(null)

async function handleUpdate(propertyDefinitionId: string, value: unknown) {
  savingId.value = propertyDefinitionId
  try {
    await persistValue(propertyDefinitionId, value)
  } catch (err: unknown) {
    if (handlePreviewReadOnlyError(err)) return
    const message = (err as { data?: { statusMessage?: string } })?.data?.statusMessage ?? 'Failed to save'
    toast.error(message)
  } finally {
    savingId.value = null
  }
}

const ICON_MAP: Record<PropertyType, unknown> = {
  text: TextIcon,
  long_text: AlignLeft,
  number: Hash,
  select: CircleDot,
  multi_select: List,
  date: Calendar,
  checkbox: CheckSquare,
  url: LinkIcon,
  email: Mail,
  person: User,
  file: Paperclip,
}

function iconFor(def: PropertyDefinition) {
  return ICON_MAP[def.type]
}

const editorOpen = ref(false)
const editorScope = ref<'org' | 'job'>('org')
function openEditor(scope: 'org' | 'job') {
  editorScope.value = scope
  editorOpen.value = true
}
</script>

<template>
  <section class="space-y-1">
    <!-- Read-only entries (e.g. form question responses) -->
    <template v-if="readOnlyEntries && readOnlyEntries.length">
      <div
        v-for="entry in readOnlyEntries"
        :key="`ro-${entry.definition.id}`"
        class="group grid grid-cols-[200px_1fr] items-start gap-2 rounded px-2 py-1"
      >
        <div class="flex items-center gap-1.5 pt-1 text-sm text-surface-500 dark:text-surface-400 min-w-0">
          <component :is="iconFor(entry.definition) as never" class="size-3.5 shrink-0" />
          <span class="truncate">{{ entry.definition.name }}</span>
          <span class="ml-1 rounded bg-surface-100 dark:bg-surface-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-surface-500">Form</span>
        </div>
        <div class="min-w-0 px-2 py-1">
          <PropertyValueDisplay :definition="entry.definition" :value="entry.value" />
        </div>
      </div>
      <div v-if="localEntries.length" class="my-2 border-t border-surface-100 dark:border-surface-800" />
    </template>

    <!-- Editable entries -->
    <div
      v-for="entry in localEntries"
      :key="entry.definition.id"
      class="grid grid-cols-[200px_1fr] items-start gap-2 rounded px-2 py-0.5"
    >
      <div class="flex items-center gap-1.5 pt-1.5 text-sm text-surface-500 dark:text-surface-400 min-w-0">
        <component :is="iconFor(entry.definition) as never" class="size-3.5 shrink-0" />
        <span class="truncate">{{ entry.definition.name }}</span>
        <span
          v-if="entry.definition.jobId"
          class="ml-1 rounded bg-brand-50 dark:bg-brand-950/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-brand-600 dark:text-brand-300"
          title="Defined for this job only"
        >Job</span>
      </div>
      <div class="min-w-0">
        <PropertyValueEditor
          :definition="entry.definition"
          :model-value="entry.value"
          :saving="savingId === entry.definition.id"
          @update="(v) => handleUpdate(entry.definition.id, v)"
        />
      </div>
    </div>

    <!-- Management affordances -->
    <div v-if="!managementDisabled" class="flex items-center gap-2 pt-1">
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-surface-500 hover:text-surface-800 dark:hover:text-surface-100 hover:bg-surface-100 dark:hover:bg-surface-800 cursor-pointer"
        @click="openEditor('org')"
      >
        <Plus class="size-3.5" /> Add org-wide property
      </button>
      <button
        v-if="jobId && entityType === 'application'"
        type="button"
        class="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-surface-500 hover:text-surface-800 dark:hover:text-surface-100 hover:bg-surface-100 dark:hover:bg-surface-800 cursor-pointer"
        @click="openEditor('job')"
      >
        <Settings2 class="size-3.5" /> Manage job-specific properties
      </button>
    </div>

    <PropertySchemaEditor
      :open="editorOpen"
      :entity-type="entityType"
      :job-id="editorScope === 'job' ? jobId ?? null : null"
      @close="editorOpen = false"
      @changed="emit('refresh')"
    />
  </section>
</template>
