<script setup lang="ts">
import {
  AlignLeft, Calendar, CheckSquare, CircleDot, Hash, Link as LinkIcon,
  List, Mail, Paperclip, Text as TextIcon, User,
} from 'lucide-vue-next'
import {
  PROPERTY_COLOR_CLASSES,
  type PropertyDefinition,
  type PropertyType,
} from '~~/shared/properties'

const props = defineProps<{
  definition: PropertyDefinition
  value: unknown
  /** Truncate single-line values when shown in dense places (lists, chips). */
  compact?: boolean
}>()

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

const isEmpty = computed(() => {
  const v = props.value
  if (v === null || v === undefined || v === '') return true
  if (Array.isArray(v) && v.length === 0) return true
  return false
})

const config = computed(() => props.definition.config as { options?: { id: string; label: string; color: keyof typeof PROPERTY_COLOR_CLASSES }[]; format?: 'plain' | 'percent' | 'currency'; currency?: string } | null)

const numberDisplay = computed(() => {
  if (props.definition.type !== 'number') return ''
  const n = Number(props.value)
  if (!Number.isFinite(n)) return ''
  const cfg = config.value
  if (cfg?.format === 'percent') return `${n}%`
  if (cfg?.format === 'currency') return `${cfg.currency ?? '$'}${n.toLocaleString()}`
  return n.toLocaleString()
})

const selectOption = computed(() => {
  if (props.definition.type !== 'select') return null
  const id = props.value as string
  return config.value?.options?.find((o) => o.id === id) ?? null
})

const multiSelectOptions = computed(() => {
  if (props.definition.type !== 'multi_select') return []
  const ids = (props.value as string[]) ?? []
  return ids
    .map((id) => config.value?.options?.find((o) => o.id === id))
    .filter((o): o is NonNullable<typeof o> => Boolean(o))
})

const dateDisplay = computed(() => {
  if (props.definition.type !== 'date') return ''
  if (typeof props.value !== 'string') return ''
  const d = new Date(`${props.value}T00:00:00`)
  if (isNaN(d.getTime())) return props.value
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
})

defineExpose({ icon: ICON_MAP[props.definition.type] })
</script>

<template>
  <span class="inline-flex min-w-0 items-center gap-1.5 text-sm">
    <span v-if="isEmpty" class="text-surface-300 dark:text-surface-600 select-none" aria-label="Empty">—</span>

    <!-- text / long_text / person -->
    <span
      v-else-if="definition.type === 'text' || definition.type === 'long_text' || definition.type === 'person'"
      class="text-surface-800 dark:text-surface-100"
      :class="compact ? 'truncate' : 'whitespace-pre-wrap'"
    >{{ value }}</span>

    <!-- number -->
    <span v-else-if="definition.type === 'number'" class="font-mono tabular-nums text-surface-800 dark:text-surface-100">
      {{ numberDisplay }}
    </span>

    <!-- checkbox -->
    <span v-else-if="definition.type === 'checkbox'" class="text-surface-800 dark:text-surface-100">
      <CheckSquare v-if="value" class="size-4 text-green-600" />
      <span v-else class="size-4 inline-block rounded border border-surface-300 dark:border-surface-700" />
    </span>

    <!-- date -->
    <span v-else-if="definition.type === 'date'" class="text-surface-800 dark:text-surface-100">{{ dateDisplay }}</span>

    <!-- url -->
    <a
      v-else-if="definition.type === 'url'"
      :href="(value as string)"
      target="_blank"
      rel="noopener noreferrer"
      class="text-brand-600 hover:underline truncate"
      @click.stop
    >{{ value }}</a>

    <!-- email -->
    <a
      v-else-if="definition.type === 'email'"
      :href="`mailto:${value}`"
      class="text-brand-600 hover:underline truncate"
      @click.stop
    >{{ value }}</a>

    <!-- select -->
    <span
      v-else-if="definition.type === 'select' && selectOption"
      class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      :class="PROPERTY_COLOR_CLASSES[selectOption.color].chip"
    >{{ selectOption.label }}</span>

    <!-- multi_select -->
    <span v-else-if="definition.type === 'multi_select'" class="flex flex-wrap items-center gap-1">
      <span
        v-for="opt in multiSelectOptions"
        :key="opt.id"
        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
        :class="PROPERTY_COLOR_CLASSES[opt.color].chip"
      >{{ opt.label }}</span>
    </span>

    <!-- file -->
    <span v-else-if="definition.type === 'file'" class="inline-flex items-center gap-1 text-surface-700 dark:text-surface-200">
      <Paperclip class="size-3.5" />
      <span class="truncate">Attached</span>
    </span>
  </span>
</template>
