// ─────────────────────────────────────────────
// Shared types for custom properties (client + server)
// ─────────────────────────────────────────────

export const PROPERTY_ENTITY_TYPES = ['candidate', 'application'] as const
export type PropertyEntityType = (typeof PROPERTY_ENTITY_TYPES)[number]

export const PROPERTY_TYPES = [
  'text', 'long_text', 'number', 'select', 'multi_select',
  'date', 'checkbox', 'url', 'email', 'person', 'file',
] as const
export type PropertyType = (typeof PROPERTY_TYPES)[number]

export const PROPERTY_OPTION_COLORS = [
  'gray', 'red', 'orange', 'amber', 'yellow', 'green', 'teal',
  'blue', 'indigo', 'violet', 'pink',
] as const
export type PropertyOptionColor = (typeof PROPERTY_OPTION_COLORS)[number]

export interface PropertySelectOption {
  id: string
  label: string
  color: PropertyOptionColor
}

export interface PropertySelectConfig {
  options: PropertySelectOption[]
}

export interface PropertyNumberConfig {
  format: 'plain' | 'percent' | 'currency'
  currency?: string
}

export type PropertyConfig =
  | PropertySelectConfig
  | PropertyNumberConfig
  | Record<string, unknown>
  | null

export interface PropertyDefinition {
  id: string
  organizationId: string
  jobId: string | null
  entityType: PropertyEntityType
  type: PropertyType
  name: string
  description: string | null
  displayOrder: number
  config: PropertyConfig
  createdAt: string
  updatedAt: string
}

export interface PropertyEntry {
  definition: PropertyDefinition
  value: unknown
}

// ── Type-specific value shapes ──
export type PropertyTextValue = string | null
export type PropertyNumberValue = number | null
export type PropertyCheckboxValue = boolean | null
export type PropertyDateValue = string | null
export type PropertySelectValue = string | null
export type PropertyMultiSelectValue = string[] | null
export type PropertyFileValue = { documentId: string } | null

export type PropertyOperator =
  | 'equals'
  | 'contains'
  | 'in'
  | 'isEmpty'
  | 'isNotEmpty'

export interface PropertyFilter {
  propertyDefinitionId: string
  op: PropertyOperator
  value?: unknown
}

// ── Display helpers (pure, importable from anywhere) ──

export function isEmptyPropertyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value) && value.length === 0) return true
  return false
}

export function formatPropertyValueAsText(
  type: PropertyType,
  value: unknown,
  config: PropertyConfig,
): string {
  if (isEmptyPropertyValue(value)) return ''
  switch (type) {
    case 'text':
    case 'long_text':
    case 'url':
    case 'email':
    case 'date':
      return String(value)
    case 'number': {
      const n = Number(value)
      if (!Number.isFinite(n)) return ''
      const cfg = (config as PropertyNumberConfig | null) ?? null
      if (cfg?.format === 'percent') return `${n}%`
      if (cfg?.format === 'currency') return `${cfg.currency ?? '$'}${n.toLocaleString()}`
      return n.toLocaleString()
    }
    case 'checkbox':
      return value ? 'Yes' : 'No'
    case 'select': {
      const opts = (config as PropertySelectConfig | null)?.options ?? []
      return opts.find((o) => o.id === value)?.label ?? ''
    }
    case 'multi_select': {
      const opts = (config as PropertySelectConfig | null)?.options ?? []
      const ids = (value as string[]) ?? []
      return ids.map((id) => opts.find((o) => o.id === id)?.label ?? '').filter(Boolean).join(', ')
    }
    case 'person':
      return String(value)
    case 'file':
      return (value as { documentId?: string } | null)?.documentId ?? ''
  }
}

export const PROPERTY_TYPE_LABELS: Record<PropertyType, string> = {
  text: 'Text',
  long_text: 'Text (long)',
  number: 'Number',
  select: 'Select',
  multi_select: 'Multi-select',
  date: 'Date',
  checkbox: 'Checkbox',
  url: 'URL',
  email: 'Email',
  person: 'Person',
  file: 'File',
}

export const PROPERTY_COLOR_CLASSES: Record<
  PropertyOptionColor,
  { chip: string; dot: string }
> = {
  gray: { chip: 'bg-surface-100 text-surface-700 dark:bg-surface-800 dark:text-surface-200', dot: 'bg-surface-400' },
  red: { chip: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300', dot: 'bg-rose-500' },
  orange: { chip: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300', dot: 'bg-orange-500' },
  amber: { chip: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300', dot: 'bg-amber-500' },
  yellow: { chip: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-300', dot: 'bg-yellow-400' },
  green: { chip: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300', dot: 'bg-green-500' },
  teal: { chip: 'bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300', dot: 'bg-teal-500' },
  blue: { chip: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300', dot: 'bg-blue-500' },
  indigo: { chip: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300', dot: 'bg-indigo-500' },
  violet: { chip: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300', dot: 'bg-violet-500' },
  pink: { chip: 'bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300', dot: 'bg-pink-500' },
}
