<script setup lang="ts">
import { Briefcase, Building2, MapPin } from 'lucide-vue-next'

defineProps<{
  job: {
    title: string
    description?: string | null
    location?: string | null
    type: string
    organizationName?: string | null
  }
}>()

const typeLabels: Record<string, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contract: 'Contract',
  internship: 'Internship',
}
</script>

<template>
  <div class="mb-6 overflow-hidden rounded-2xl border border-surface-200 bg-white shadow-sm dark:border-surface-800 dark:bg-surface-900">
    <div class="h-1 bg-gradient-to-r from-brand-500 to-brand-400" />

    <div class="p-6 sm:p-8">
      <div class="mb-4 flex flex-wrap items-center gap-2">
        <span
          v-if="job.organizationName"
          class="inline-flex items-center gap-1.5 rounded-full border border-surface-200 bg-surface-50 px-3 py-1 text-xs font-medium text-surface-700 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-300"
        >
          <Building2 class="size-3.5 text-surface-400" />
          {{ job.organizationName }}
        </span>
        <span class="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 dark:border-brand-900 dark:bg-brand-950 dark:text-brand-300">
          <Briefcase class="size-3.5" />
          {{ typeLabels[job.type] ?? job.type }}
        </span>
        <span
          v-if="job.location"
          class="inline-flex items-center gap-1.5 rounded-full border border-surface-200 bg-surface-50 px-3 py-1 text-xs font-medium text-surface-600 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-400"
        >
          <MapPin class="size-3.5 text-surface-400" />
          {{ job.location }}
        </span>
      </div>

      <h1 class="text-2xl font-bold tracking-tight text-surface-900 dark:text-surface-50 sm:text-3xl">
        {{ job.title }}
      </h1>

      <div v-if="job.description" class="mt-5 border-t border-surface-100 pt-5 dark:border-surface-800">
        <MarkdownDescription :value="job.description" />
      </div>
    </div>
  </div>
</template>
