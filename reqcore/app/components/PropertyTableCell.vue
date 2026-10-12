<script setup lang="ts">
import type { PropertyDefinition, PropertyEntityType, PropertyEntry } from '~~/shared/properties'

/**
 * PropertyTableCell — inline-editable property cell for list/table views.
 *
 * Wraps PropertyValueEditor with per-row optimistic mutations so that editing
 * a property value in the table doesn't require a full page refresh.
 * Click events are stopped to prevent row navigation while editing.
 */

const props = defineProps<{
  entityType: PropertyEntityType
  entityId: string
  definition: PropertyDefinition
  value: unknown
}>()

const toast = useToast()
const { handlePreviewReadOnlyError } = usePreviewReadOnly()

// Local single-entry ref for useEntityPropertyMutations
const localEntries = ref<PropertyEntry[]>([
  { definition: props.definition, value: props.value },
])

// Keep in sync if parent data refreshes
watch(
  () => props.value,
  (next) => {
    localEntries.value = [{ definition: props.definition, value: next }]
  },
)

const { setValue } = useEntityPropertyMutations({
  entityType: props.entityType,
  entityId: () => props.entityId,
  entries: localEntries,
})

const savingId = ref<string | null>(null)

async function handleUpdate(value: unknown) {
  savingId.value = props.definition.id
  try {
    await setValue(props.definition.id, value)
  } catch (err: unknown) {
    if (handlePreviewReadOnlyError(err)) return
    const message = (err as { data?: { statusMessage?: string } })?.data?.statusMessage ?? 'Failed to save'
    toast.error(message)
  } finally {
    savingId.value = null
  }
}

const currentValue = computed(() => localEntries.value[0]?.value ?? null)
</script>

<template>
  <!-- stop click so row navigation doesn't fire when editing -->
  <div @click.stop>
    <PropertyValueEditor
      :definition="definition"
      :model-value="currentValue"
      :saving="savingId === definition.id"
      @update="handleUpdate"
    />
  </div>
</template>
