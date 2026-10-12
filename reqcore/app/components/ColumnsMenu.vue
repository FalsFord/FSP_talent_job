<script setup lang="ts">
import { Columns2, Check } from 'lucide-vue-next'

const props = defineProps<{
  columns: { key: string; label: string; required?: boolean }[]
  modelValue: Record<string, boolean>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, boolean>]
}>()

const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

function toggle(key: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: !props.modelValue[key] })
}

function handleClickOutside(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

watch(open, (val) => {
  if (val) document.addEventListener('click', handleClickOutside)
  else document.removeEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

const hiddenCount = computed(() =>
  props.columns.filter(col => !col.required && !props.modelValue[col.key]).length,
)
</script>

<template>
  <div ref="menuRef" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
      :class="hiddenCount > 0
        ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-950 dark:text-brand-300'
        : 'border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 text-surface-600 dark:text-surface-400 hover:bg-surface-50 dark:hover:bg-surface-800'"
      @click.stop="open = !open"
    >
      <Columns2 class="size-4" />
      Columns
      <span
        v-if="hiddenCount > 0"
        class="inline-flex items-center justify-center min-w-[1rem] h-4 px-1 rounded-full bg-brand-600 text-white text-[10px] font-semibold"
      >{{ hiddenCount }}</span>
    </button>

    <div
      v-if="open"
      class="absolute right-0 z-50 mt-1 w-48 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 shadow-lg py-1"
    >
      <div class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-surface-400 dark:text-surface-500 border-b border-surface-100 dark:border-surface-800 mb-1">
        Toggle columns
      </div>
      <button
        v-for="col in columns"
        :key="col.key"
        type="button"
        class="flex w-full items-center gap-2.5 px-3 py-1.5 text-sm transition-colors"
        :class="col.required
          ? 'text-surface-400 dark:text-surface-500 cursor-not-allowed'
          : 'text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800'"
        :disabled="col.required"
        @click="!col.required && toggle(col.key)"
      >
        <span
          class="flex size-4 shrink-0 items-center justify-center rounded border transition-colors"
          :class="(col.required || modelValue[col.key])
            ? 'bg-brand-600 border-brand-600 text-white'
            : 'border-surface-300 dark:border-surface-600'"
        >
          <Check v-if="col.required || modelValue[col.key]" class="size-3" />
        </span>
        {{ col.label }}
      </button>
    </div>
  </div>
</template>
