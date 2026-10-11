<script setup lang="ts" generic="T extends Record<string, unknown>">
import { Bookmark, Star, Trash2, Plus, Check, ChevronDown } from 'lucide-vue-next'
import type { SavedView } from '~/composables/useSavedViews'

const props = defineProps<{
  views: SavedView<T>[]
  activeViewId: string | null
  /** Whether current settings differ from the active view (i.e. unsaved edits). */
  isDirty?: boolean
}>()

const emit = defineEmits<{
  'select': [id: string | null]
  'save': [name: string]
  'update': [id: string]
  'delete': [id: string]
  'set-default': [id: string | null]
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const showSaveForm = ref(false)
const newName = ref('')
const nameInput = ref<HTMLInputElement | null>(null)

const activeView = computed(() => props.views.find(v => v.id === props.activeViewId) ?? null)

const buttonLabel = computed(() => {
  if (activeView.value) return activeView.value.name
  return 'Views'
})

function toggle() {
  open.value = !open.value
  if (!open.value) showSaveForm.value = false
}

function close() {
  open.value = false
  showSaveForm.value = false
  newName.value = ''
}

function handleOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) close()
}

onMounted(() => {
  document.addEventListener('mousedown', handleOutside)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutside)
  document.removeEventListener('keydown', onKeydown)
})

function selectView(id: string | null) {
  emit('select', id)
  close()
}

async function openSaveForm() {
  showSaveForm.value = true
  newName.value = activeView.value?.name ? `${activeView.value.name} (copy)` : `View ${props.views.length + 1}`
  await nextTick()
  nameInput.value?.focus()
  nameInput.value?.select()
}

function submitSave() {
  const name = newName.value.trim()
  if (!name) return
  emit('save', name)
  close()
}

function onUpdate(id: string, e: Event) {
  e.stopPropagation()
  emit('update', id)
  close()
}

function onSetDefault(id: string, isDefault: boolean | undefined, e: Event) {
  e.stopPropagation()
  emit('set-default', isDefault ? null : id)
}

function onDelete(id: string, e: Event) {
  e.stopPropagation()
  emit('delete', id)
}
</script>

<template>
  <div ref="rootRef" class="relative inline-block">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
      :class="activeViewId
        ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-950 dark:text-brand-300'
        : 'border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 text-surface-600 dark:text-surface-400 hover:bg-surface-50 dark:hover:bg-surface-800'"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="toggle"
    >
      <Bookmark class="size-4" :class="activeView?.isDefault ? 'fill-current text-amber-500' : ''" />
      <span class="max-w-[160px] truncate">{{ buttonLabel }}</span>
      <span
        v-if="isDirty && activeViewId"
        class="size-1.5 rounded-full bg-amber-500"
        title="Unsaved changes"
      />
      <ChevronDown class="size-3.5 opacity-60" />
    </button>

    <!-- Dropdown -->
    <div
      v-if="open"
      class="absolute left-0 top-full mt-1.5 z-30 w-72 rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 shadow-xl overflow-hidden"
      role="menu"
    >
      <!-- "All / no view" -->
      <button
        type="button"
        class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors"
        :class="!activeViewId
          ? 'bg-brand-50 dark:bg-brand-950 text-brand-700 dark:text-brand-300'
          : 'text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800'"
        @click="selectView(null)"
      >
        <Check class="size-3.5" :class="!activeViewId ? '' : 'opacity-0'" />
        <span class="flex-1">All (no view)</span>
      </button>

      <!-- Saved views -->
      <div v-if="views.length > 0" class="max-h-72 overflow-y-auto border-t border-surface-100 dark:border-surface-800">
        <div
          v-for="v in views"
          :key="v.id"
          class="group flex items-center gap-1 pl-3 pr-1.5 py-1.5 text-sm transition-colors"
          :class="activeViewId === v.id
            ? 'bg-brand-50 dark:bg-brand-950'
            : 'hover:bg-surface-50 dark:hover:bg-surface-800'"
        >
          <button
            type="button"
            class="flex-1 flex items-center gap-2 text-left min-w-0 py-0.5"
            :class="activeViewId === v.id ? 'text-brand-700 dark:text-brand-300' : 'text-surface-700 dark:text-surface-300'"
            @click="selectView(v.id)"
          >
            <Check class="size-3.5 shrink-0" :class="activeViewId === v.id ? '' : 'opacity-0'" />
            <Star
              v-if="v.isDefault"
              class="size-3.5 shrink-0 text-amber-500 fill-current"
              title="Default view"
            />
            <span class="truncate flex-1">{{ v.name }}</span>
          </button>

          <!-- Save changes -->
          <button
            v-if="activeViewId === v.id && isDirty"
            type="button"
            class="rounded p-1 text-surface-400 hover:text-success-600 hover:bg-success-50 dark:hover:bg-success-950 transition-colors"
            title="Save current changes to this view"
            @click="(e) => onUpdate(v.id, e)"
          >
            <Check class="size-3.5" />
          </button>
          <!-- Set default -->
          <button
            type="button"
            class="rounded p-1 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
            :class="v.isDefault ? 'text-amber-500' : 'opacity-0 group-hover:opacity-100 hover:text-amber-500'"
            :title="v.isDefault ? 'Remove as default' : 'Set as default'"
            @click="(e) => onSetDefault(v.id, v.isDefault, e)"
          >
            <Star class="size-3.5" :class="v.isDefault ? 'fill-current' : ''" />
          </button>
          <!-- Delete -->
          <button
            type="button"
            class="rounded p-1 text-surface-400 hover:text-danger-600 hover:bg-danger-50 dark:hover:bg-danger-950 transition-colors opacity-0 group-hover:opacity-100"
            title="Delete view"
            @click="(e) => onDelete(v.id, e)"
          >
            <Trash2 class="size-3.5" />
          </button>
        </div>
      </div>

      <!-- Footer: save form -->
      <div class="border-t border-surface-100 dark:border-surface-800 bg-surface-50/60 dark:bg-surface-800/40 p-2">
        <form v-if="showSaveForm" class="flex items-center gap-1.5" @submit.prevent="submitSave">
          <input
            ref="nameInput"
            v-model="newName"
            type="text"
            placeholder="View name"
            maxlength="60"
            class="flex-1 rounded-md border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900 px-2.5 py-1.5 text-sm text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            @keydown.escape.prevent="showSaveForm = false; newName = ''"
          />
          <button
            type="submit"
            :disabled="!newName.trim()"
            class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >Save</button>
        </form>
        <button
          v-else
          type="button"
          class="w-full flex items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950 transition-colors"
          @click="openSaveForm"
        >
          <Plus class="size-3.5" />
          {{ activeViewId && isDirty ? 'Save as new view' : 'Save current view' }}
        </button>
      </div>
    </div>
  </div>
</template>
