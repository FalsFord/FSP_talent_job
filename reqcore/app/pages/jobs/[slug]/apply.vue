<script setup lang="ts">
import { Briefcase } from 'lucide-vue-next'

definePageMeta({
  layout: 'public',
})

const route = useRoute()
const jobSlug = route.params.slug as string
const { track } = useTrack()
const { t } = useI18n()

// Capture source tracking params from the URL
const sourceRef = (route.query.ref as string) || undefined
const utmSource = (route.query.utm_source as string) || undefined
const utmMedium = (route.query.utm_medium as string) || undefined
const utmCampaign = (route.query.utm_campaign as string) || undefined
const utmTerm = (route.query.utm_term as string) || undefined
const utmContent = (route.query.utm_content as string) || undefined

onMounted(() => track('application_started', { slug: jobSlug }))

// Fetch public job data (no auth needed)
const { data: job, status: fetchStatus, error: fetchError } = useFetch(
  `/api/public/jobs/${jobSlug}`,
  { key: `public-job-${jobSlug}` },
)

useSeoMeta({
  title: computed(() => job.value ? `Apply — ${job.value.title}` : 'Apply — Reqcore'),
  description: computed(() => job.value?.description?.slice(0, 160) ?? 'Submit your application'),
  robots: 'noindex, nofollow',
})

// ─────────────────────────────────────────────
// Form state
// ─────────────────────────────────────────────

const form = ref({
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  website: '', // honeypot
})

// Dynamic question responses: questionId → value
const responses = ref<Record<string, string | string[] | number | boolean>>({})

// File uploads: questionId → File object
const fileUploads = ref<Record<string, File>>({})

// Built-in document uploads (resume) and cover letter text
const resumeFile = ref<File | null>(null)
const coverLetterText = ref('')

const isSubmitting = ref(false)
const errors = ref<Record<string, string>>({})
const submitError = ref<string | null>(null)

/** Whether the form has any file_upload type questions OR built-in document fields */
const hasFileQuestions = computed(() => {
  const hasCustomFileQ = job.value?.questions?.some((q: { type: string }) => q.type === 'file_upload') ?? false
  const hasBuiltInFiles = !!resumeFile.value
  return hasCustomFileQ || hasBuiltInFiles
})

/**
 * Handle file selection from DynamicField.
 * Stores the File object separately from the model value.
 */
function handleFileSelected(questionId: string, file: File | null) {
  if (file) {
    fileUploads.value[questionId] = file
  } else {
    delete fileUploads.value[questionId]
  }
}

function validate(): boolean {
  errors.value = {}
  const maxSize = 10 * 1024 * 1024

  if (!form.value.firstName.trim()) errors.value.firstName = 'First name is required'
  if (!form.value.lastName.trim()) errors.value.lastName = 'Last name is required'
  if (!form.value.email.trim()) {
    errors.value.email = 'Email is required'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.value.email)) {
    errors.value.email = 'Invalid email address'
  }
  if (job.value?.phoneRequirement === 'required' && !form.value.phone.trim()) {
    errors.value.phone = 'Phone number is required'
  }

  // Validate required resume
  if (job.value?.requireResume && !resumeFile.value) {
    errors.value.resume = 'Resume/CV is required'
  }

  // Validate required cover letter
  if (job.value?.requireCoverLetter && !coverLetterText.value.trim()) {
    errors.value.coverLetter = 'Cover letter is required'
  } else if (coverLetterText.value.length > 10_000) {
    errors.value.coverLetter = 'Cover letter must be 10,000 characters or fewer.'
  }

  // Validate resume file size
  if (resumeFile.value && resumeFile.value.size > maxSize) {
    errors.value.resume = 'File too large. Maximum 10 MB.'
  }

  // Validate required custom questions
  if (job.value?.questions) {
    for (const q of job.value.questions) {
      if (q.required) {
        if (q.type === 'file_upload') {
          // For file uploads, check if a File was selected
          if (!fileUploads.value[q.id]) {
            errors.value[`q-${q.id}`] = 'This field is required'
          }
        } else {
          const val = responses.value[q.id]
          const isEmpty = val === undefined || val === null || val === '' ||
            (Array.isArray(val) && val.length === 0)

          if (isEmpty) {
            errors.value[`q-${q.id}`] = 'This field is required'
          }
        }
      }
    }
  }

  // Validate custom file upload sizes
  for (const [questionId, file] of Object.entries(fileUploads.value)) {
    if (file.size > maxSize) {
      errors.value[`q-${questionId}`] = 'File too large. Maximum 10 MB.'
    }
  }

  return Object.keys(errors.value).length === 0
}

async function handleSubmit() {
  submitError.value = null
  if (!validate()) return

  isSubmitting.value = true
  try {
    // Build responses array from the map (exclude file_upload questions — those go as files)
    const fileQuestionIds = new Set(
      job.value?.questions
        ?.filter((q: { type: string }) => q.type === 'file_upload')
        .map((q: { id: string }) => q.id) ?? [],
    )

    const responseArray = Object.entries(responses.value)
      .filter(([questionId, value]) => {
        if (fileQuestionIds.has(questionId)) return false
        if (value === undefined || value === null || value === '') return false
        if (Array.isArray(value) && value.length === 0) return false
        return true
      })
      .map(([questionId, value]) => ({ questionId, value }))

    // Determine if we need FormData (any files present — custom or built-in)
    const hasAnyFiles = Object.keys(fileUploads.value).length > 0
      || !!resumeFile.value

    if (hasAnyFiles) {
      // Use FormData when files are present
      const formData = new FormData()
      formData.append('firstName', form.value.firstName.trim())
      formData.append('lastName', form.value.lastName.trim())
      formData.append('email', form.value.email.trim())
      if (job.value?.phoneRequirement !== 'hidden' && form.value.phone.trim()) {
        formData.append('phone', form.value.phone.trim())
      }
      if (form.value.website) {
        formData.append('website', form.value.website)
      }

      // Serialize non-file responses as JSON
      formData.append('responses', JSON.stringify(responseArray))

      // Append custom question files
      for (const [questionId, file] of Object.entries(fileUploads.value)) {
        formData.append(`file:${questionId}`, file)
      }

      // Append built-in resume
      if (resumeFile.value) {
        formData.append('resume', resumeFile.value)
      }
      // Append cover letter text
      if (coverLetterText.value.trim()) {
        formData.append('coverLetterText', coverLetterText.value.trim())
      }

      // Source tracking params
      if (sourceRef) formData.append('ref', sourceRef)
      if (utmSource) formData.append('utmSource', utmSource)
      if (utmMedium) formData.append('utmMedium', utmMedium)
      if (utmCampaign) formData.append('utmCampaign', utmCampaign)
      if (utmTerm) formData.append('utmTerm', utmTerm)
      if (utmContent) formData.append('utmContent', utmContent)

      await $fetch(`/api/public/jobs/${jobSlug}/apply`, {
        method: 'POST',
        body: formData,
      })
    } else {
      // No files — use JSON as before
      await $fetch(`/api/public/jobs/${jobSlug}/apply`, {
        method: 'POST',
        body: {
          firstName: form.value.firstName.trim(),
          lastName: form.value.lastName.trim(),
          email: form.value.email.trim(),
          phone: job.value?.phoneRequirement !== 'hidden' ? (form.value.phone.trim() || undefined) : undefined,
          website: form.value.website, // honeypot
          coverLetterText: coverLetterText.value.trim() || undefined,
          responses: responseArray,
          ref: sourceRef,
          utmSource,
          utmMedium,
          utmCampaign,
          utmTerm,
          utmContent,
        },
      })
    }

    track('application_submitted', { slug: jobSlug })
    await navigateTo(`/jobs/${jobSlug}/confirmation`)
  } catch (err: any) {
    const message = err.data?.statusMessage ?? 'Something went wrong. Please try again.'
    submitError.value = message

    // Surface file-related errors next to the resume field so the user knows what to fix
    const status = err.data?.statusCode ?? err.statusCode
    if (status === 400 && message.toLowerCase().includes('resume')) {
      errors.value.resume = message
    } else if (status === 502 && message.toLowerCase().includes('resume')) {
      errors.value.resume = message
    }
  } finally {
    isSubmitting.value = false
  }
}

</script>

<template>
  <div>
    <!-- Loading skeleton -->
    <div v-if="fetchStatus === 'pending'" class="animate-pulse space-y-4">
      <div class="h-7 w-48 bg-surface-200 dark:bg-surface-800 rounded-lg" />
      <div class="h-5 w-32 bg-surface-200 dark:bg-surface-800 rounded-full" />
      <div class="h-4 w-64 bg-surface-200 dark:bg-surface-800 rounded" />
      <div class="mt-8 h-48 bg-surface-200 dark:bg-surface-800 rounded-xl" />
    </div>

    <!-- Not found / not open -->
    <div v-else-if="fetchError" class="flex flex-col items-center justify-center py-20 text-center">
      <div class="mb-5 flex size-16 items-center justify-center rounded-full bg-surface-100 dark:bg-surface-800">
        <Briefcase class="size-7 text-surface-400" />
      </div>
      <h1 class="text-xl font-bold text-surface-900 dark:text-surface-100 mb-2">Position Not Found</h1>
      <p class="text-sm text-surface-500 mb-6 max-w-xs">
        This position may have been filled or is no longer accepting applications.
      </p>
      <a
        :href="useRuntimeConfig().public.marketingUrl"
        class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700 transition-colors shadow-sm"
      >
        Back to Home
      </a>
    </div>

    <!-- Application form -->
    <template v-else-if="job">

      <!-- Back link -->
      <NuxtLink
        :to="$localePath(`/jobs/${jobSlug}`)"
        class="inline-flex items-center gap-1.5 text-sm text-surface-500 hover:text-surface-800 dark:hover:text-surface-200 transition-colors mb-6 group"
      >
        <svg class="size-3.5 transition-transform group-hover:-translate-x-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="m15 18-6-6 6-6"/>
        </svg>
        Back to job details
      </NuxtLink>

      <PublicJobApplicationHeader :job="job" />

      <!-- Application form card -->
      <ApplicationFormBody
        v-model:form="form"
        v-model:responses="responses"
        v-model:resume="resumeFile"
        v-model:cover-letter="coverLetterText"
        :job="job"
        :errors="errors"
        :submit-error="submitError"
        :is-submitting="isSubmitting"
        @file-selected="handleFileSelected"
        @clear-error="(key) => delete errors[key]"
        @submit="handleSubmit"
      />

      <!-- GDPR privacy notice (org-configurable) -->
      <p
        v-if="job.privacyPolicyText || job.privacyPolicyUrl || job.privacyContactEmail"
        class="mt-6 text-xs leading-relaxed text-surface-400 dark:text-surface-500"
      >
        <template v-if="job.privacyPolicyText">{{ job.privacyPolicyText }} </template>
        <template v-else>
          {{ t('retention.privacy.defaultNotice', { organization: job.organizationName || t('retention.privacy.thisOrganization') }) }}
        </template>
        <a
          v-if="job.privacyPolicyUrl"
          :href="job.privacyPolicyUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="text-brand-600 hover:underline"
        >{{ t('retention.privacy.policyLink') }}</a><template v-if="job.privacyPolicyUrl && job.privacyContactEmail"> · </template>
        <a
          v-if="job.privacyContactEmail"
          :href="`mailto:${job.privacyContactEmail}`"
          class="text-brand-600 hover:underline"
        >{{ t('retention.privacy.contactLabel') }}: {{ job.privacyContactEmail }}</a>
      </p>
    </template>
  </div>
</template>
