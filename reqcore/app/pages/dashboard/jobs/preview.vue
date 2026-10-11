<script setup lang="ts">
import { ArrowLeft, Eye, RefreshCw } from 'lucide-vue-next'

definePageMeta({
  layout: 'public',
  middleware: ['auth', 'require-org'],
})

useSeoMeta({
  title: 'Draft application preview',
  description: 'Preview an unpublished job application form',
  robots: 'noindex, nofollow',
})

type DraftQuestion = {
  id: string
  label: string
  type: string
  description?: string | null
  required: boolean
  options?: string[] | null
}

type JobDraft = {
  form: {
    title: string
    description?: string
    location?: string
    type: string
  }
  applicationForm: {
    phoneRequirement?: 'hidden' | 'optional' | 'required'
    requireResume: boolean
    requireCoverLetter: boolean
    questions: DraftQuestion[]
  }
}

const JOB_DRAFT_STORAGE_KEY = 'reqcore-job-draft'
const draft = ref<JobDraft | null>(null)
const isReady = ref(false)
const submitError = ref<string | null>(null)
const { activeOrg } = useCurrentOrg()

const form = ref({
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  website: '',
})
const responses = ref<Record<string, string | string[] | number | boolean>>({})
const resumeFile = ref<File | null>(null)
const coverLetterText = ref('')

const previewJob = computed(() => {
  if (!draft.value) return null

  return {
    ...draft.value.form,
    ...draft.value.applicationForm,
    phoneRequirement: draft.value.applicationForm.phoneRequirement ?? 'optional',
    organizationName: activeOrg.value?.name ?? null,
  }
})

function loadDraft() {
  isReady.value = false
  submitError.value = null

  try {
    const raw = localStorage.getItem(JOB_DRAFT_STORAGE_KEY)
    if (!raw) {
      draft.value = null
      return
    }

    const parsed = JSON.parse(raw) as Partial<JobDraft>
    if (!parsed.form?.title || !parsed.applicationForm) {
      draft.value = null
      return
    }

    draft.value = parsed as JobDraft
  } catch {
    draft.value = null
  } finally {
    isReady.value = true
  }
}

function closePreview() {
  window.close()
}

function handlePreviewSubmit() {
  submitError.value = 'This is a draft preview. Applications cannot be submitted until the job is published.'
}

onMounted(loadDraft)
</script>

<template>
  <div>
    <div
      class="mb-6 flex flex-col gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-4 py-3 dark:border-brand-900 dark:bg-brand-950/50 sm:flex-row sm:items-center sm:justify-between"
    >
      <div class="flex items-start gap-3">
        <span class="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-900 dark:text-brand-300">
          <Eye class="size-4" />
        </span>
        <div>
          <p class="text-sm font-semibold text-brand-900 dark:text-brand-100">Draft applicant preview</p>
          <p class="text-xs text-brand-700 dark:text-brand-300">Only you can see this page. Changes appear after reopening or refreshing the preview.</p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-white px-3 py-2 text-xs font-medium text-brand-800 transition-colors hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-200 dark:hover:bg-brand-900"
          @click="loadDraft"
        >
          <RefreshCw class="size-3.5" />
          Refresh draft
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:text-brand-300 dark:hover:bg-brand-900"
          @click="closePreview"
        >
          <ArrowLeft class="size-3.5" />
          Back to editor
        </button>
      </div>
    </div>

    <div v-if="!isReady" class="animate-pulse space-y-4">
      <div class="h-48 rounded-2xl bg-surface-200 dark:bg-surface-800" />
      <div class="h-96 rounded-2xl bg-surface-200 dark:bg-surface-800" />
    </div>

    <div v-else-if="!previewJob" class="rounded-2xl border border-surface-200 bg-white px-6 py-16 text-center shadow-sm dark:border-surface-800 dark:bg-surface-900">
      <h1 class="text-lg font-semibold text-surface-900 dark:text-surface-100">No draft preview found</h1>
      <p class="mx-auto mt-2 max-w-md text-sm text-surface-500">
        Return to the job builder, add a job title, and click “View preview” again.
      </p>
      <button
        type="button"
        class="mt-5 inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
        @click="closePreview"
      >
        <ArrowLeft class="size-4" />
        Back to editor
      </button>
    </div>

    <template v-else>
      <PublicJobApplicationHeader :job="previewJob" />

      <ApplicationFormBody
        v-model:form="form"
        v-model:responses="responses"
        v-model:resume="resumeFile"
        v-model:cover-letter="coverLetterText"
        :job="previewJob"
        :submit-error="submitError"
        @clear-error="submitError = null"
        @submit="handlePreviewSubmit"
      />
    </template>
  </div>
</template>
