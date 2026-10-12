<script setup lang="ts">
import { ShieldAlert, Save, Check, Loader2, Trash2, RotateCcw, ShieldOff, Download } from 'lucide-vue-next'

definePageMeta({})
const { t } = useI18n()

useSeoMeta({
  title: () => `${t('retention.title')} — Reqcore`,
  description: () => t('retention.description'),
})

const { allowed: canManage } = usePermission({ candidate: ['delete'] })
const { allowed: canUpdateOrg } = usePermission({ organization: ['update'] })
const { settings, updateSettings, formatDateTime } = useOrgSettings()

// ── Policy form state ──
const enabled = ref(false)
const months = ref<number | null>(24)
const quarantineDays = ref<number | null>(30)
const policyUrl = ref('')
const policyText = ref('')
const contactEmail = ref('')

watch(settings, (s) => {
  if (!s) return
  enabled.value = s.retentionEnabled ?? false
  months.value = s.retentionMonths ?? 24
  quarantineDays.value = s.quarantineDays ?? 30
  policyUrl.value = s.privacyPolicyUrl ?? ''
  policyText.value = s.privacyPolicyText ?? ''
  contactEmail.value = s.privacyContactEmail ?? ''
}, { immediate: true })

const isSaving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

type IntegerField = 'months' | 'quarantineDays'

function handleIntegerInput(event: Event, field: IntegerField) {
  const input = event.target as HTMLInputElement
  const digits = input.value.replace(/\D/g, '')

  // Keep the rendered value in sync even when Vue's numeric value is unchanged.
  input.value = digits
  const value = digits === '' ? null : Number(digits)

  if (field === 'months') months.value = value
  else quarantineDays.value = value
}

function normalizeIntegerField(field: IntegerField, min: number, max: number, fallback: number) {
  const current = field === 'months' ? months.value : quarantineDays.value
  const normalized = Math.min(max, Math.max(min, current ?? fallback))

  if (field === 'months') months.value = normalized
  else quarantineDays.value = normalized

  return normalized
}

async function handleSave() {
  if (!canUpdateOrg.value) return
  const retentionMonths = normalizeIntegerField('months', 1, 120, 24)
  const retentionQuarantineDays = normalizeIntegerField('quarantineDays', 0, 365, 30)
  isSaving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    await updateSettings({
      retentionEnabled: enabled.value,
      retentionMonths,
      quarantineDays: retentionQuarantineDays,
      privacyPolicyUrl: policyUrl.value || null,
      privacyPolicyText: policyText.value || null,
      privacyContactEmail: contactEmail.value || null,
    })
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  }
  catch (err: unknown) {
    saveError.value = err instanceof Error ? err.message : t('retention.errors.save')
  }
  finally {
    isSaving.value = false
  }
}

// ── Review list ──
interface ReviewItem {
  id: string
  name: string
  email: string
  status: 'expiring' | 'expired' | 'quarantined' | 'exempt'
  expiresAt: string
  quarantinedAt: string | null
  scheduledPurgeAt: string | null
  exemptUntil: string | null
  exemptReason: string | null
}

const { data: review, refresh: refreshReview, status: reviewStatus } = useFetch<{
  cleanupEnabled: boolean
  retentionEnabled: boolean
  retentionMonths: number
  count: number
  items: ReviewItem[]
}>('/api/admin/retention/review', {
  headers: useRequestHeaders(['cookie']),
})

const actionError = ref('')

async function restore(id: string) {
  actionError.value = ''
  try {
    await $fetch(`/api/candidates/${id}/restore`, { method: 'POST' })
    await refreshReview()
  }
  catch (err: unknown) {
    actionError.value = err instanceof Error ? err.message : t('retention.errors.restore')
  }
}

async function exempt(id: string) {
  actionError.value = ''
  const reason = window.prompt(t('retention.actions.holdPrompt'))
  if (reason === null) return
  // Exempt for 12 months from now.
  const until = new Date()
  until.setFullYear(until.getFullYear() + 1)
  try {
    await $fetch(`/api/candidates/${id}/retention`, {
      method: 'PATCH',
      body: { exemptUntil: until.toISOString(), reason },
    })
    await refreshReview()
  }
  catch (err: unknown) {
    actionError.value = err instanceof Error ? err.message : t('retention.errors.hold')
  }
}

async function clearExemption(id: string) {
  actionError.value = ''
  try {
    await $fetch(`/api/candidates/${id}/retention`, {
      method: 'PATCH',
      body: { exemptUntil: null },
    })
    await refreshReview()
  }
  catch (err: unknown) {
    actionError.value = err instanceof Error ? err.message : t('retention.errors.clearHold')
  }
}

async function eraseNow(id: string, name: string) {
  actionError.value = ''
  // Permanent erasure is irreversible — require the operator to type the exact
  // name so it can never happen on a stray click.
  const typed = window.prompt(t('retention.actions.eraseConfirm', { name }))
  if (typed === null) return
  if (typed.trim() !== name.trim()) {
    actionError.value = t('retention.errors.eraseNameMismatch')
    return
  }
  try {
    await $fetch(`/api/candidates/${id}?permanent=true`, { method: 'DELETE' })
    await refreshReview()
  }
  catch (err: unknown) {
    actionError.value = err instanceof Error ? err.message : t('retention.errors.erase')
  }
}

function exportData(id: string) {
  window.open(`/api/candidates/${id}/export`, '_blank')
}

const statusStyles: Record<ReviewItem['status'], string> = {
  expiring: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800',
  expired: 'bg-orange-50 dark:bg-orange-950/40 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800',
  quarantined: 'bg-danger-50 dark:bg-danger-950/40 text-danger-700 dark:text-danger-400 border-danger-200 dark:border-danger-800',
  exempt: 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 border-surface-200 dark:border-surface-700',
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6">
    <div class="mb-2">
      <h1 class="text-lg font-semibold text-surface-900 dark:text-surface-50">{{ t('retention.title') }}</h1>
      <p class="text-sm text-surface-500 dark:text-surface-400 mt-0.5">
        {{ t('retention.description') }}
      </p>
    </div>

    <!-- Retention policy -->
    <section class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 overflow-hidden">
      <div class="px-4 sm:px-6 py-5 border-b border-surface-200 dark:border-surface-800">
        <div class="flex items-center gap-3">
          <div class="flex items-center justify-center size-10 shrink-0 rounded-lg bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-400">
            <ShieldAlert class="size-5" />
          </div>
          <div>
            <h2 class="text-base font-semibold text-surface-900 dark:text-surface-100">{{ t('retention.policy.title') }}</h2>
            <p class="text-sm text-surface-500 dark:text-surface-400">{{ t('retention.policy.description') }}</p>
          </div>
        </div>
      </div>

      <div class="px-4 sm:px-6 py-5 space-y-5">
        <label class="flex items-start gap-3 cursor-pointer">
          <input v-model="enabled" type="checkbox" class="mt-0.5 accent-brand-600" :disabled="!canUpdateOrg" />
          <span>
            <span class="block text-sm font-medium text-surface-800 dark:text-surface-200">{{ t('retention.policy.enable') }}</span>
            <span class="block text-xs text-surface-400 mt-0.5">{{ t('retention.policy.enableHelp') }}</span>
          </span>
        </label>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">{{ t('retention.policy.months') }}</label>
            <input :value="months ?? ''" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="3"
              aria-valuemin="1" aria-valuemax="120" :disabled="!canUpdateOrg"
              @input="handleIntegerInput($event, 'months')"
              @blur="normalizeIntegerField('months', 1, 120, 24)"
              class="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">{{ t('retention.policy.quarantineDays') }}</label>
            <input :value="quarantineDays ?? ''" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="3"
              aria-valuemin="0" aria-valuemax="365" :disabled="!canUpdateOrg"
              @input="handleIntegerInput($event, 'quarantineDays')"
              @blur="normalizeIntegerField('quarantineDays', 0, 365, 30)"
              class="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-3 py-2 text-sm" />
            <p class="text-xs text-surface-400 mt-1">{{ t('retention.policy.quarantineHelp') }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Privacy notice -->
    <section class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 overflow-hidden">
      <div class="px-4 sm:px-6 py-5 border-b border-surface-200 dark:border-surface-800">
        <h2 class="text-base font-semibold text-surface-900 dark:text-surface-100">{{ t('retention.privacy.title') }}</h2>
        <p class="text-sm text-surface-500 dark:text-surface-400">{{ t('retention.privacy.description') }}</p>
      </div>
      <div class="px-4 sm:px-6 py-5 space-y-4">
        <div>
          <label class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">{{ t('retention.privacy.url') }}</label>
          <input v-model="policyUrl" type="url" placeholder="https://example.com/privacy" :disabled="!canUpdateOrg"
            class="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">{{ t('retention.privacy.email') }}</label>
          <input v-model="contactEmail" type="email" placeholder="privacy@example.com" :disabled="!canUpdateOrg"
            class="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">{{ t('retention.privacy.text') }}</label>
          <textarea v-model="policyText" rows="3" placeholder="We process your application data to evaluate your candidacy…" :disabled="!canUpdateOrg"
            class="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-3 py-2 text-sm" />
        </div>
      </div>
    </section>

    <div v-if="saveError" class="rounded-lg border border-danger-200 dark:border-danger-800 bg-danger-50 dark:bg-danger-950 px-4 py-3 text-sm text-danger-700 dark:text-danger-400">
      {{ saveError }}
    </div>
    <div class="flex items-center gap-3">
      <button :disabled="!canUpdateOrg || isSaving"
        class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        @click="handleSave">
        <Check v-if="saveSuccess" class="size-4" />
        <Loader2 v-else-if="isSaving" class="size-4 animate-spin" />
        <Save v-else class="size-4" />
        {{ saveSuccess ? t('retention.save.saved') : isSaving ? t('retention.save.saving') : t('retention.save.button') }}
      </button>
      <p v-if="!canUpdateOrg" class="text-xs text-surface-400">{{ t('retention.save.permission') }}</p>
    </div>

    <!-- Upcoming-deletion review -->
    <section class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 overflow-hidden">
      <div class="px-4 sm:px-6 py-5 border-b border-surface-200 dark:border-surface-800">
        <h2 class="text-base font-semibold text-surface-900 dark:text-surface-100">{{ t('retention.review.title') }}</h2>
        <p class="text-sm text-surface-500 dark:text-surface-400">{{ t('retention.review.description') }}</p>
      </div>

      <div class="px-4 sm:px-6 py-5">
        <div
          v-if="review && !review.cleanupEnabled"
          class="mb-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 px-4 py-3 text-sm text-amber-700 dark:text-amber-400"
        >
          {{ t('retention.review.instanceDisabled') }}
        </div>
        <div v-if="actionError" class="mb-4 rounded-lg border border-danger-200 dark:border-danger-800 bg-danger-50 dark:bg-danger-950 px-4 py-3 text-sm text-danger-700 dark:text-danger-400">
          {{ actionError }}
        </div>

        <div v-if="reviewStatus === 'pending'" class="flex items-center gap-2 text-sm text-surface-400">
          <Loader2 class="size-4 animate-spin" /> {{ t('retention.review.loading') }}
        </div>
        <p v-else-if="!review?.items?.length" class="text-sm text-surface-400">{{ t('retention.review.empty') }}</p>

        <ul v-else class="divide-y divide-surface-100 dark:divide-surface-800">
          <li v-for="item in review.items" :key="item.id" class="py-3 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-surface-900 dark:text-surface-100 truncate">{{ item.name }}</span>
                <span class="shrink-0 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize" :class="statusStyles[item.status]">
                  {{ t(`retention.status.${item.status}`) }}
                </span>
              </div>
              <p class="text-xs text-surface-400 truncate">{{ item.email }}</p>
              <p v-if="item.status === 'quarantined' && item.scheduledPurgeAt" class="text-xs text-danger-500 mt-0.5">
                {{ t('retention.review.erases', { date: formatDateTime(item.scheduledPurgeAt) }) }}
              </p>
              <p v-else-if="item.status === 'exempt' && item.exemptUntil" class="text-xs text-surface-400 mt-0.5">
                {{ t('retention.review.exemptUntil', { date: formatDateTime(item.exemptUntil) }) }}<template v-if="item.exemptReason"> — {{ item.exemptReason }}</template>
              </p>
              <p v-else class="text-xs text-surface-400 mt-0.5">{{ t('retention.review.expires', { date: formatDateTime(item.expiresAt) }) }}</p>
            </div>

            <div v-if="canManage" class="flex shrink-0 items-center gap-1">
              <button :title="t('retention.actions.export')" class="rounded-md p-1.5 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-700" @click="exportData(item.id)">
                <Download class="size-4" />
              </button>
              <button v-if="item.status === 'quarantined'" :title="t('retention.actions.restore')" class="rounded-md p-1.5 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-brand-600" @click="restore(item.id)">
                <RotateCcw class="size-4" />
              </button>
              <button v-if="item.status === 'exempt'" :title="t('retention.actions.clearHold')" class="rounded-md p-1.5 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-700" @click="clearExemption(item.id)">
                <ShieldOff class="size-4" />
              </button>
              <button v-else :title="t('retention.actions.hold')" class="rounded-md p-1.5 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-700" @click="exempt(item.id)">
                <ShieldOff class="size-4" />
              </button>
              <button :title="t('retention.actions.erase')" class="rounded-md p-1.5 text-surface-400 hover:bg-danger-50 dark:hover:bg-danger-950 hover:text-danger-600" @click="eraseNow(item.id, item.name)">
                <Trash2 class="size-4" />
              </button>
            </div>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
