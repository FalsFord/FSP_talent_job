<script setup lang="ts">
import { Filter, Plus, X } from 'lucide-vue-next'
import {
  PROPERTY_COLOR_CLASSES,
  type PropertyDefinition,
  type PropertyEntityType,
  type PropertyFilter,
  type PropertyOperator,
} from '~~/shared/properties'

/**
 * PropertyFilterBar — chip-style filter UI for list pages.
 *
 * Holds an array of `PropertyFilter` and emits `update:modelValue` whenever
 * a filter is added, removed, or modified. The parent serializes this to
 * the `propertyFilters` query string param to send to the list endpoint.
 */

const props = defineProps<{
  modelValue: PropertyFilter[]
  entityType: PropertyEntityType
  /** Optional jobId to also include per-job application properties in the picker. */
  jobId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: PropertyFilter[]): void
}>()

const { definitions } = useProperties({
  entityType: () => props.entityType,
  jobId: () => props.jobId ?? null,
})

const definitionMap = computed(() => {
  const map = new Map<string, PropertyDefinition>()
  for (const d of definitions.value) map.set(d.id, d)
  return map
})

const pickerOpen = ref(false)
const pickerEl = ref<HTMLElement | null>(null)

function closePickerOnOutside(e: PointerEvent) {
  if (!pickerOpen.value || !pickerEl.value) return
  if (!pickerEl.value.contains(e.target as Node)) pickerOpen.value = false
}
watchEffect((onCleanup) => {
  if (pickerOpen.value && import.meta.client) {
    document.addEventListener('pointerdown', closePickerOnOutside, true)
    onCleanup(() => document.removeEventListener('pointerdown', closePickerOnOutside, true))
  }
})

function defaultOpFor(def: PropertyDefinition): PropertyOperator {
  switch (def.type) {
    case 'select':
    case 'checkbox':
      return 'equals'
    case 'multi_select':
      return 'in'
    case 'text':
    case 'long_text':
    case 'url':
    case 'email':
    case 'person':
      return 'contains'
    default:
      return 'isNotEmpty'
  }
}

function operatorsFor(def: PropertyDefinition): PropertyOperator[] {
  switch (def.type) {
    case 'select':
      return ['equals', 'isNotEmpty']
    case 'multi_select':
      return ['in', 'isNotEmpty']
    case 'checkbox':
      return ['equals']
    case 'text':
    case 'long_text':
    case 'url':
    case 'email':
    case 'person':
      return ['contains', 'equals', 'isNotEmpty']
    case 'number':
    case 'date':
      return ['equals', 'isNotEmpty']
    case 'file':
      return ['isNotEmpty']
  }
}

const OPERATOR_LABELS: Record<PropertyOperator, string> = {
  equals: 'is',
  contains: 'contains',
  in: 'is any of',
  isEmpty: 'is empty',
  isNotEmpty: 'is set',
}

function addFilter(def: PropertyDefinition) {
  const op = defaultOpFor(def)
  const next: PropertyFilter = {
    propertyDefinitionId: def.id,
    op,
    value: op === 'equals' && def.type === 'checkbox' ? true : op === 'in' ? [] : '',
  }
  emit('update:modelValue', [...props.modelValue, next])
  pickerOpen.value = false
}

function removeFilter(idx: number) {
  const next = props.modelValue.filter((_, i) => i !== idx)
  emit('update:modelValue', next)
}

function patchFilter(idx: number, patch: Partial<PropertyFilter>) {
  const next = props.modelValue.map((f, i) => (i === idx ? { ...f, ...patch } : f))
  emit('update:modelValue', next)
}

function clearAll() {
  emit('update:modelValue', [])
}

const editingIdx = ref<number | null>(null)
const editEl = ref<HTMLElement | null>(null)
function setEditElRef(el: Element | ComponentPublicInstance | null, filterIdx: number) {
  if (editingIdx.value === filterIdx) editEl.value = el as HTMLElement | null
}
function closeEditOnOutside(e: PointerEvent) {
  if (editingIdx.value === null || !editEl.value) return
  if (!editEl.value.contains(e.target as Node)) editingIdx.value = null
}
watchEffect((onCleanup) => {
  if (editingIdx.value !== null && import.meta.client) {
    document.addEventListener('pointerdown', closeEditOnOutside, true)
    onCleanup(() => document.removeEventListener('pointerdown', closeEditOnOutside, true))
  }
})

function summarizeFilter(f: PropertyFilter): string {
  const def = definitionMap.value.get(f.propertyDefinitionId)
  if (!def) return ''
  const opLabel = OPERATOR_LABELS[f.op]
  if (f.op === 'isEmpty' || f.op === 'isNotEmpty') return `${def.name} ${opLabel}`
  if (f.op === 'in') {
    const ids = (f.value as string[]) ?? []
    const opts = (def.config as { options?: { id: string; label: string }[] } | null)?.options ?? []
    const labels = ids.map((id) => opts.find((o) => o.id === id)?.label).filter(Boolean)
    return `${def.name} ${opLabel} ${labels.join(', ') || '…'}`
  }
  if (def.type === 'select') {
    const opts = (def.config as { options?: { id: string; label: string }[] } | null)?.options ?? []
    const label = opts.find((o) => o.id === f.value)?.label ?? '…'
    return `${def.name} ${opLabel} ${label}`
  }
  if (def.type === 'checkbox') return `${def.name} ${opLabel} ${f.value ? 'checked' : 'unchecked'}`
  return `${def.name} ${opLabel} ${f.value || '…'}`
}

const showableDefs = computed(() => definitions.value)
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <!-- Existing filter chips -->
    <div
      v-for="(f, idx) in modelValue"
      :key="`${f.propertyDefinitionId}-${idx}`"
      class="relative"
    >
      <div
        class="inline-flex items-center rounded-full border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/40 text-xs font-medium text-brand-700 dark:text-brand-200 hover:bg-brand-100 dark:hover:bg-brand-950"
      >
        <button
          type="button"
          class="inline-flex items-center gap-1.5 pl-2.5 pr-1 py-1 cursor-pointer"
          :aria-label="`Edit filter: ${summarizeFilter(f)}`"
          @click="editingIdx = editingIdx === idx ? null : idx"
        >
          <span class="max-w-[20rem] truncate">{{ summarizeFilter(f) }}</span>
        </button>
        <button
          type="button"
          class="pr-2 pl-1 py-1 text-brand-500 hover:text-brand-700 cursor-pointer"
          :aria-label="`Remove filter: ${summarizeFilter(f)}`"
          @click.stop="removeFilter(idx)"
        >
          <X class="size-3" />
        </button>
      </div>

      <!-- Edit popover -->
      <div
        v-if="editingIdx === idx"
        :ref="(el) => setEditElRef(el, idx)"
        class="absolute left-0 top-full z-30 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 p-3 shadow-lg"
      >
        <template v-if="definitionMap.get(f.propertyDefinitionId) as PropertyDefinition">
          <div class="space-y-2">
            <div class="text-xs font-semibold text-surface-700 dark:text-surface-200">
              {{ definitionMap.get(f.propertyDefinitionId)!.name }}
            </div>
            <select
              :value="f.op"
              class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm text-surface-900 dark:text-surface-50 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
              @change="(e) => patchFilter(idx, { op: (e.target as HTMLSelectElement).value as PropertyOperator })"
            >
              <option v-for="op in operatorsFor(definitionMap.get(f.propertyDefinitionId)!)" :key="op" :value="op">
                {{ OPERATOR_LABELS[op] }}
              </option>
            </select>

            <!-- Value input by op + type -->
            <template v-if="!['isEmpty', 'isNotEmpty'].includes(f.op)">
              <!-- select equals -->
              <select
                v-if="definitionMap.get(f.propertyDefinitionId)!.type === 'select' && f.op === 'equals'"
                :value="(f.value as string) ?? ''"
                class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                @change="(e) => patchFilter(idx, { value: (e.target as HTMLSelectElement).value || null })"
              >
                <option value="">—</option>
                <option v-for="opt in ((definitionMap.get(f.propertyDefinitionId)!.config as { options?: { id: string; label: string }[] } | null)?.options ?? [])" :key="opt.id" :value="opt.id">
                  {{ opt.label }}
                </option>
              </select>

              <!-- multi_select in -->
              <div v-else-if="definitionMap.get(f.propertyDefinitionId)!.type === 'multi_select' && f.op === 'in'" class="flex flex-wrap gap-1">
                <button
                  v-for="opt in ((definitionMap.get(f.propertyDefinitionId)!.config as { options?: { id: string; label: string; color: keyof typeof PROPERTY_COLOR_CLASSES }[] } | null)?.options ?? [])"
                  :key="opt.id"
                  type="button"
                  class="cursor-pointer rounded-full px-2 py-0.5 text-xs font-medium transition-opacity"
                  :class="[PROPERTY_COLOR_CLASSES[opt.color].chip, ((f.value as string[]) ?? []).includes(opt.id) ? '' : 'opacity-50 hover:opacity-100']"
                  @click="() => {
                    const arr = ((f.value as string[]) ?? []).slice()
                    const i = arr.indexOf(opt.id)
                    if (i >= 0) arr.splice(i, 1); else arr.push(opt.id)
                    patchFilter(idx, { value: arr })
                  }"
                >{{ opt.label }}</button>
              </div>

              <!-- checkbox equals -->
              <select
                v-else-if="definitionMap.get(f.propertyDefinitionId)!.type === 'checkbox'"
                :value="String(f.value ?? false)"
                class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                @change="(e) => patchFilter(idx, { value: (e.target as HTMLSelectElement).value === 'true' })"
              >
                <option value="true">checked</option>
                <option value="false">unchecked</option>
              </select>

              <!-- date / number equals -->
              <input
                v-else-if="definitionMap.get(f.propertyDefinitionId)!.type === 'date' && f.op === 'equals'"
                type="date"
                :value="(f.value as string) ?? ''"
                class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                @change="(e) => patchFilter(idx, { value: (e.target as HTMLInputElement).value || null })"
              />
              <input
                v-else-if="definitionMap.get(f.propertyDefinitionId)!.type === 'number' && f.op === 'equals'"
                type="number"
                step="any"
                :value="(f.value as number) ?? ''"
                class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                @input="(e) => { const v = (e.target as HTMLInputElement).value; patchFilter(idx, { value: v === '' ? null : Number(v) }) }"
              />

              <!-- default text -->
              <input
                v-else
                type="text"
                :value="(f.value as string) ?? ''"
                placeholder="Value"
                class="w-full rounded border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2 py-1 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                @input="(e) => patchFilter(idx, { value: (e.target as HTMLInputElement).value })"
              />
            </template>
          </div>
        </template>
      </div>
    </div>

    <!-- Add filter -->
    <div class="relative" ref="pickerEl">
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded-full border border-dashed border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2.5 py-1 text-xs font-medium text-surface-500 hover:text-surface-800 hover:border-surface-400 dark:hover:text-surface-100 cursor-pointer"
        @click="pickerOpen = !pickerOpen"
      >
        <component :is="modelValue.length === 0 ? Filter : Plus" class="size-3.5" />
        {{ modelValue.length === 0 ? 'Filter' : 'Add filter' }}
      </button>
      <div
        v-if="pickerOpen"
        class="absolute left-0 top-full z-30 mt-1 w-64 max-w-[calc(100vw-2rem)] rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 shadow-lg"
      >
        <div class="max-h-72 overflow-y-auto py-1">
          <button
            v-for="def in showableDefs"
            :key="def.id"
            type="button"
            class="flex w-full cursor-pointer items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-surface-100 dark:hover:bg-surface-800"
            @click="addFilter(def)"
          >
            <span class="truncate text-surface-800 dark:text-surface-100">{{ def.name }}</span>
            <span class="text-[10px] uppercase tracking-wide text-surface-400">{{ def.type }}</span>
          </button>
          <div v-if="showableDefs.length === 0" class="px-3 py-2 text-xs text-surface-400">
            No properties to filter by yet.
          </div>
        </div>
      </div>
    </div>

    <button
      v-if="modelValue.length > 0"
      type="button"
      class="text-xs text-surface-500 hover:text-surface-800 dark:hover:text-surface-100 cursor-pointer"
      @click="clearAll"
    >Clear all</button>
  </div>
</template>
