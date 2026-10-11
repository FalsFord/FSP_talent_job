<script setup lang="ts">
import { X, RotateCcw, Bookmark, Plus, Check } from 'lucide-vue-next'

const props = defineProps<{
  modelValue: boolean
  title?: string
  description?: string
  activeCount?: number
  /** Show the "Save as view" affordance in the footer. */
  saveable?: boolean
  /** Suggested default name when saving a new view. */
  defaultSaveName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'reset': []
  'save-view': [name: string]
}>()

function close() {
  emit('update:modelValue', false)
}

const showSaveForm = ref(false)
const newName = ref('')
const nameInput = ref<HTMLInputElement | null>(null)

async function openSaveForm() {
  showSaveForm.value = true
  newName.value = props.defaultSaveName ?? 'New view'
  await nextTick()
  nameInput.value?.focus()
  nameInput.value?.select()
}

function submitSave() {
  const name = newName.value.trim()
  if (!name) return
  emit('save-view', name)
  showSaveForm.value = false
  newName.value = ''
}

// Reset save form when drawer closes
watch(() => props.modelValue, (open) => {
  if (!open) {
    showSaveForm.value = false
    newName.value = ''
  }
})

// Lock body scroll while open
watch(() => props.modelValue, (open) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = open ? 'hidden' : ''
})

// Close on Escape
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) close()
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (typeof document !== 'undefined') document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        v-if="modelValue"
        class="fixed inset-0 z-[55] bg-surface-900/40"
        @click="close"
      />
    </Transition>

    <Transition
      enter-active-class="transition-transform duration-300 ease-out"
      leave-active-class="transition-transform duration-200 ease-in"
      enter-from-class="translate-x-full"
      leave-to-class="translate-x-full"
    >
      <aside
        v-if="modelValue"
        class="fixed inset-y-0 right-0 z-[60] w-full max-w-md flex flex-col bg-white dark:bg-surface-900 shadow-2xl border-l border-surface-200 dark:border-surface-800"
        role="dialog"
        aria-modal="true"
        :aria-label="title || 'Filters'"
      >
        <!-- Header -->
        <header class="flex items-start justify-between gap-3 px-5 py-4 border-b border-surface-200 dark:border-surface-800">
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-surface-900 dark:text-surface-50 flex items-center gap-2">
              {{ title || 'Filters' }}
              <span
                v-if="activeCount && activeCount > 0"
                class="inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-brand-600 text-white text-xs font-semibold"
              >{{ activeCount }}</span>
            </h2>
            <p v-if="description" class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
              {{ description }}
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-md p-1.5 text-surface-400 hover:text-surface-900 dark:hover:text-surface-100 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
            aria-label="Close"
            @click="close"
          >
            <X class="size-4" />
          </button>
        </header>

        <!-- Body (scrollable) -->
        <div class="flex-1 overflow-y-auto px-5 py-4">
          <slot />
        </div>

        <!-- Footer -->
        <footer class="border-t border-surface-200 dark:border-surface-800 bg-surface-50/60 dark:bg-surface-800/40">
          <!-- Inline save-view form -->
          <div v-if="saveable && showSaveForm" class="flex items-center gap-2 px-5 py-3 border-b border-surface-200 dark:border-surface-800">
            <Bookmark class="size-4 text-brand-600 shrink-0" />
            <input
              ref="nameInput"
              v-model="newName"
              type="text"
              placeholder="Name this view"
              maxlength="60"
              class="flex-1 rounded-md border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2.5 py-1.5 text-sm text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              @keydown.enter.prevent="submitSave"
              @keydown.escape.prevent="showSaveForm = false; newName = ''"
            />
            <button
              type="button"
              :disabled="!newName.trim()"
              class="inline-flex items-center gap-1 rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              @click="submitSave"
            >
              <Check class="size-3.5" />
              Save
            </button>
            <button
              type="button"
              class="rounded-md p-1.5 text-surface-400 hover:text-surface-700 dark:hover:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
              aria-label="Cancel"
              @click="showSaveForm = false; newName = ''"
            >
              <X class="size-3.5" />
            </button>
          </div>

          <div class="flex items-center justify-between gap-2 px-5 py-3">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 text-xs font-medium text-surface-500 dark:text-surface-400 hover:text-danger-600 dark:hover:text-danger-400 transition-colors"
              @click="emit('reset')"
            >
              <RotateCcw class="size-3.5" />
              Reset all
            </button>
            <div class="flex items-center gap-2">
              <button
                v-if="saveable && !showSaveForm"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 px-3 py-2 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                @click="openSaveForm"
              >
                <Plus class="size-3.5" />
                Save as view
              </button>
              <slot name="footer">
                <button
                  type="button"
                  class="rounded-lg bg-surface-900 dark:bg-surface-100 px-4 py-2 text-sm font-medium text-white dark:text-surface-900 hover:opacity-90 transition-opacity"
                  @click="close"
                >
                  Done
                </button>
              </slot>
            </div>
          </div>
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>
