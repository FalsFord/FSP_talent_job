<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import {
  PROPERTY_COLOR_CLASSES,
  type PropertyDefinition,
} from '~~/shared/properties'

/**
 * PropertyValueEditor — inline-editable cell for a single property value.
 *
 * UX:
 *  - Renders PropertyValueDisplay when not editing (click to edit).
 *  - Single-line types commit on Enter/blur, cancel on Escape.
 *  - Multi-line and option pickers use a popover that closes on outside click.
 *  - Disabled mode renders read-only display only (e.g. for question responses).
 */

const props = defineProps<{
  definition: PropertyDefinition
  modelValue: unknown
  /** When true, becomes a non-clickable display. */
  readOnly?: boolean
  /** Visual hint that mutation is in flight. */
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'update', value: unknown): void
}>()

type Cfg = {
  options?: { id: string; label: string; color: keyof typeof PROPERTY_COLOR_CLASSES }[]
  format?: 'plain' | 'percent' | 'currency'
  currency?: string
} | null

const config = computed<Cfg>(() => props.definition.config as Cfg)

const editing = ref(false)
const draft = ref<unknown>(null)
const inputEl = ref<HTMLElement | null>(null)
const rootEl = ref<HTMLElement | null>(null)

// Popover positioning (Teleported to body to escape `overflow:hidden/auto`
// ancestors such as the table wrapper).
const popoverStyle = ref<Record<string, string>>({})
const POPOVER_WIDTH = 256 // matches w-64

function updatePopoverPosition() {
  if (!rootEl.value || !import.meta.client) return
  const rect = rootEl.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  // Prefer rendering below; flip up if not enough space
  const estimatedHeight = 280 // max-h-64 + padding
  const renderAbove = rect.bottom + estimatedHeight > vh && rect.top > estimatedHeight
  // Keep within viewport horizontally
  const left = Math.min(Math.max(8, rect.left), vw - POPOVER_WIDTH - 8)
  if (renderAbove) {
    // Anchor the *bottom* of the popover just above the trigger so the actual
    // rendered height (which may be shorter than the estimate) doesn't cause
    // the menu to float too far away.
    popoverStyle.value = {
      position: 'fixed',
      bottom: `${Math.max(8, vh - rect.top + 4)}px`,
      left: `${left}px`,
      width: `${POPOVER_WIDTH}px`,
      zIndex: '70',
    }
  } else {
    popoverStyle.value = {
      position: 'fixed',
      top: `${rect.bottom + 4}px`,
      left: `${left}px`,
      width: `${POPOVER_WIDTH}px`,
      zIndex: '70',
    }
  }
}

function startEdit() {
  if (props.readOnly) return
  if (editing.value) return // already open (e.g. popover types keep the display visible)
  draft.value = cloneDraft(props.modelValue)
  editing.value = true
  nextTick(() => {
    const el = inputEl.value as HTMLInputElement | HTMLTextAreaElement | null
    el?.focus()
    if (el && 'select' in el && typeof el.select === 'function') el.select()
    if (props.definition.type === 'select' || props.definition.type === 'multi_select') {
      updatePopoverPosition()
    }
  })
}

function cloneDraft(v: unknown): unknown {
  if (Array.isArray(v)) return [...v]
  return v ?? null
}

function commit(value?: unknown) {
  if (!editing.value) return
  const next = arguments.length > 0 ? value : draft.value
  editing.value = false
  // Normalize empties for clear-on-save UX
  const cleaned =
    next === '' || (Array.isArray(next) && next.length === 0) ? null : next
  // Only emit if changed
  if (JSON.stringify(cleaned ?? null) !== JSON.stringify(props.modelValue ?? null)) {
    emit('update', cleaned)
  }
}

function cancel() {
  editing.value = false
}

// Outside click handling for popover-style editors
function onDocPointerDown(e: PointerEvent) {
  if (!editing.value || !rootEl.value) return
  const target = e.target as Node | null
  if (!target) return
  if (rootEl.value.contains(target)) return
  // Also ignore clicks inside the teleported popover (which lives outside rootEl).
  const popover = document.querySelector('[data-property-popover="true"]')
  if (popover && popover.contains(target)) return
  commit()
}

function onWindowReposition() {
  if (editing.value && (props.definition.type === 'select' || props.definition.type === 'multi_select')) {
    updatePopoverPosition()
  }
}

watchEffect((onCleanup) => {
  if (editing.value && import.meta.client) {
    document.addEventListener('pointerdown', onDocPointerDown, true)
    window.addEventListener('scroll', onWindowReposition, true)
    window.addEventListener('resize', onWindowReposition)
    onCleanup(() => {
      document.removeEventListener('pointerdown', onDocPointerDown, true)
      window.removeEventListener('scroll', onWindowReposition, true)
      window.removeEventListener('resize', onWindowReposition)
    })
  }
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    cancel()
  } else if (e.key === 'Enter' && !e.shiftKey && props.definition.type !== 'long_text') {
    e.preventDefault()
    commit()
  }
}

// Multi-select toggle
function toggleMultiSelect(optionId: string) {
  const arr = Array.isArray(draft.value) ? [...(draft.value as string[])] : []
  const idx = arr.indexOf(optionId)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(optionId)
  draft.value = arr
}

const isCheckboxType = computed(() => props.definition.type === 'checkbox')
const isPopoverType = computed(
  () => props.definition.type === 'select' || props.definition.type === 'multi_select',
)
</script>

<template>
  <!-- Checkbox: instant toggle, no edit mode -->
  <div
    v-if="isCheckboxType"
    class="inline-flex items-center"
  >
    <button
      type="button"
      :disabled="readOnly"
      class="flex size-5 cursor-pointer items-center justify-center rounded border transition-colors disabled:cursor-not-allowed"
      :class="[
        modelValue
          ? 'bg-brand-600 border-brand-600 hover:bg-brand-700 hover:border-brand-700'
          : 'border-surface-300 dark:border-surface-600 hover:border-surface-400 dark:hover:border-surface-500',
        saving ? 'pointer-events-none opacity-60' : ''
      ]"
      @click="emit('update', !modelValue)"
    >
      <Check v-if="modelValue" class="size-3.5 text-white" />
    </button>
  </div>

  <div v-else ref="rootEl" class="relative w-full min-w-0">
    <!-- Display mode (also stays visible while a teleported popover is open). -->
    <button
      v-if="!editing || isPopoverType"
      type="button"
      :disabled="readOnly"
      class="group block w-full min-w-0 cursor-text rounded px-2 py-1 text-left transition-colors hover:bg-surface-100/80 dark:hover:bg-surface-800/50 disabled:cursor-default disabled:hover:bg-transparent"
      :class="[{ 'opacity-60': saving }, editing && isPopoverType ? 'ring-2 ring-brand-500/30' : '']"
      @click="startEdit"
    >
      <PropertyValueDisplay :definition="definition" :value="modelValue" />
    </button>

    <!-- Edit mode -->
    <template v-if="editing">
      <!-- Single-line text / url / email / person -->
      <input
        v-if="['text', 'url', 'email', 'person'].includes(definition.type)"
        ref="inputEl"
        :value="draft as string"
        :type="definition.type === 'email' ? 'email' : definition.type === 'url' ? 'url' : 'text'"
        class="w-full min-w-0 rounded border border-brand-500 bg-white dark:bg-surface-900 px-2 py-1 text-sm text-surface-900 dark:text-surface-50 outline-none ring-2 ring-brand-500/20"
        :placeholder="definition.type === 'url' ? 'https://…' : ''"
        @input="(e) => { draft = (e.target as HTMLInputElement).value }"
        @keydown="onKey"
        @blur="commit()"
      />

      <!-- Long text -->
      <textarea
        v-else-if="definition.type === 'long_text'"
        ref="inputEl"
        :value="draft as string"
        rows="3"
        class="w-full min-w-0 rounded border border-brand-500 bg-white dark:bg-surface-900 px-2 py-1.5 text-sm text-surface-900 dark:text-surface-50 outline-none ring-2 ring-brand-500/20"
        @input="(e) => { draft = (e.target as HTMLTextAreaElement).value }"
        @keydown="onKey"
        @blur="commit()"
      />

      <!-- Number -->
      <input
        v-else-if="definition.type === 'number'"
        ref="inputEl"
        :value="draft"
        type="number"
        step="any"
        class="w-full min-w-0 rounded border border-brand-500 bg-white dark:bg-surface-900 px-2 py-1 text-sm tabular-nums text-surface-900 dark:text-surface-50 outline-none ring-2 ring-brand-500/20"
        @input="(e) => { const v = (e.target as HTMLInputElement).value; draft = v === '' ? null : Number(v) }"
        @keydown="onKey"
        @blur="commit()"
      />

      <!-- Date -->
      <input
        v-else-if="definition.type === 'date'"
        ref="inputEl"
        :value="draft as string"
        type="date"
        class="w-full min-w-0 rounded border border-brand-500 bg-white dark:bg-surface-900 px-2 py-1 text-sm text-surface-900 dark:text-surface-50 outline-none ring-2 ring-brand-500/20"
        @input="(e) => { draft = (e.target as HTMLInputElement).value }"
        @keydown="onKey"
        @blur="commit()"
      />

      <!-- Select: popover with options (teleported to body to avoid table clipping) -->
      <Teleport v-else-if="definition.type === 'select'" to="body">
        <div
          data-property-popover="true"
          :style="popoverStyle"
          class="rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 shadow-lg"
        >
          <div class="max-h-64 overflow-y-auto py-1">
            <button
              v-for="opt in (config?.options ?? [])"
              :key="opt.id"
              type="button"
              class="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-100 dark:hover:bg-surface-800"
              @click="commit(opt.id)"
            >
              <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium" :class="PROPERTY_COLOR_CLASSES[opt.color].chip">
                {{ opt.label }}
              </span>
              <Check v-if="opt.id === modelValue" class="ml-auto size-3.5 text-brand-600" />
            </button>
            <button
              v-if="modelValue"
              type="button"
              class="flex w-full cursor-pointer items-center gap-2 border-t border-surface-100 dark:border-surface-800 px-3 py-1.5 text-left text-xs text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800"
              @click="commit(null)"
            >
              <X class="size-3.5" /> Clear
            </button>
            <div v-if="(config?.options ?? []).length === 0" class="px-3 py-2 text-xs text-surface-400">
              No options yet — add some in the schema editor.
            </div>
          </div>
        </div>
      </Teleport>

      <!-- Multi-select: popover with toggleable chips (teleported to body) -->
      <Teleport v-else-if="definition.type === 'multi_select'" to="body">
        <div
          data-property-popover="true"
          :style="popoverStyle"
          class="rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 shadow-lg"
        >
          <div class="max-h-64 overflow-y-auto py-1">
            <button
              v-for="opt in (config?.options ?? [])"
              :key="opt.id"
              type="button"
              class="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-100 dark:hover:bg-surface-800"
              @click="toggleMultiSelect(opt.id)"
            >
              <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium" :class="PROPERTY_COLOR_CLASSES[opt.color].chip">
                {{ opt.label }}
              </span>
              <Check v-if="(draft as string[] | null)?.includes(opt.id)" class="ml-auto size-3.5 text-brand-600" />
            </button>
            <div v-if="(config?.options ?? []).length === 0" class="px-3 py-2 text-xs text-surface-400">
              No options yet — add some in the schema editor.
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 border-t border-surface-100 dark:border-surface-800 px-2 py-1.5">
            <button type="button" class="text-xs text-surface-500 hover:text-surface-700 cursor-pointer" @click="cancel">Cancel</button>
            <button type="button" class="rounded bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700 cursor-pointer" @click="commit()">Done</button>
          </div>
        </div>
      </Teleport>

      <!-- File: not editable inline (use Documents flow) -->
      <div v-else-if="definition.type === 'file'" class="text-xs text-surface-400 italic px-2 py-1">
        File properties are managed via Documents.
      </div>
    </template>
  </div>
</template>
