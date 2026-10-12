<script setup lang="ts">
/**
 * Presentational application form — the single source of truth for how the
 * candidate-facing application renders. Used in two modes:
 *
 *  - `live`    : the real, interactive form on /jobs/[slug]/apply.
 *  - `preview` : a non-interactive replica shown inside the recruiter's
 *                application builder. Fields are inert; clicking a field group
 *                emits `edit-field` so the builder can open the matching editor.
 *
 * Keeping both modes in one component is deliberate: the recruiter preview can
 * never drift from what candidates actually see, because there is only one
 * layout. State, validation and submission live in the parent — this component
 * is purely presentation plus two-way value binding.
 */
type Question = {
  id: string
  type: string
  label: string
  description?: string | null
  required: boolean
  options?: string[] | null
}

const props = withDefaults(defineProps<{
  job: {
    phoneRequirement?: 'hidden' | 'optional' | 'required'
    requireResume?: boolean
    requireCoverLetter?: boolean
    questions?: Question[]
  }
  mode?: 'live' | 'preview'
  errors?: Record<string, string>
  submitError?: string | null
  isSubmitting?: boolean
}>(), {
  mode: 'live',
  errors: () => ({}),
  submitError: null,
  isSubmitting: false,
})

const emit = defineEmits<{
  (e: 'file-selected', questionId: string, file: File | null): void
  (e: 'clear-error', key: string): void
  (e: 'submit'): void
  /** Preview mode: the recruiter clicked a field group to edit it. */
  (e: 'edit-field', field: string): void
}>()

const form = defineModel<{
  firstName: string
  lastName: string
  email: string
  phone: string
  website: string
}>('form', { required: true })
const responses = defineModel<Record<string, string | string[] | number | boolean>>('responses', { required: true })
const resume = defineModel<File | null>('resume', { default: null })
const coverLetter = defineModel<string>('coverLetter', { default: '' })

const isPreview = computed(() => props.mode === 'preview')

/** In preview mode, clicking a field group edits it instead of focusing the input. */
function onFieldClick(field: string) {
  if (isPreview.value) emit('edit-field', field)
}
</script>

<template>
  <!-- Application form card -->
  <div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 shadow-sm overflow-hidden">
    <!-- Card header -->
    <div class="border-b border-surface-100 dark:border-surface-800 px-6 sm:px-8 py-5">
      <h2 class="text-base font-semibold text-surface-900 dark:text-surface-100">Your application</h2>
      <p class="mt-0.5 text-sm text-surface-500">Fields marked with <span class="text-danger-500">*</span> are required.</p>
    </div>

    <div class="px-6 sm:px-8 py-6 sm:py-8">
      <!-- Server error banner -->
      <div
        v-if="submitError"
        class="rounded-xl border border-danger-200 dark:border-danger-800 bg-danger-50 dark:bg-danger-950/50 px-4 py-3 text-sm text-danger-700 dark:text-danger-400 mb-6 flex items-start gap-3"
        role="alert"
      >
        <svg class="mt-0.5 size-4 shrink-0 text-danger-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>{{ submitError }}</span>
      </div>

      <form
        class="space-y-5"
        :class="isPreview ? 'select-none' : ''"
        @submit.prevent="emit('submit')"
      >
        <!-- Honeypot (hidden from humans) -->
        <div class="absolute -left-[9999px]" aria-hidden="true">
          <label for="website">Website</label>
          <input id="website" v-model="form.website" type="text" tabindex="-1" autocomplete="off" />
        </div>

        <!-- Name row -->
        <div
          class="grid grid-cols-1 sm:grid-cols-2 gap-4"
          :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
          @click="onFieldClick('name')"
        >
          <!-- First Name -->
          <div>
            <label for="firstName" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
              First Name <span class="text-danger-500">*</span>
            </label>
            <input
              id="firstName"
              v-model="form.firstName"
              type="text"
              placeholder="Jane"
              autocomplete="given-name"
              :tabindex="isPreview ? -1 : undefined"
              :class="[
                'w-full rounded-xl border px-3.5 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors',
                errors.firstName ? 'border-danger-300 dark:border-danger-700 focus:ring-danger-500 focus:border-danger-500' : 'border-surface-300 dark:border-surface-700',
                isPreview ? 'pointer-events-none' : '',
              ]"
            />
            <p v-if="errors.firstName" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
              <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {{ errors.firstName }}
            </p>
          </div>

          <!-- Last Name -->
          <div>
            <label for="lastName" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
              Last Name <span class="text-danger-500">*</span>
            </label>
            <input
              id="lastName"
              v-model="form.lastName"
              type="text"
              placeholder="Doe"
              autocomplete="family-name"
              :tabindex="isPreview ? -1 : undefined"
              :class="[
                'w-full rounded-xl border px-3.5 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors',
                errors.lastName ? 'border-danger-300 dark:border-danger-700 focus:ring-danger-500 focus:border-danger-500' : 'border-surface-300 dark:border-surface-700',
                isPreview ? 'pointer-events-none' : '',
              ]"
            />
            <p v-if="errors.lastName" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
              <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {{ errors.lastName }}
            </p>
          </div>
        </div>

        <!-- Email -->
        <div
          :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
          @click="onFieldClick('email')"
        >
          <label for="email" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
            Email <span class="text-danger-500">*</span>
          </label>
          <input
            id="email"
            v-model="form.email"
            type="email"
            placeholder="you@example.com"
            autocomplete="email"
            :tabindex="isPreview ? -1 : undefined"
            :class="[
              'w-full rounded-xl border px-3.5 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors',
              errors.email ? 'border-danger-300 dark:border-danger-700 focus:ring-danger-500 focus:border-danger-500' : 'border-surface-300 dark:border-surface-700',
              isPreview ? 'pointer-events-none' : '',
            ]"
          />
          <p v-if="errors.email" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
            <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ errors.email }}
          </p>
        </div>

        <!-- Phone -->
        <div
          v-if="job.phoneRequirement !== 'hidden'"
          :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
          @click="onFieldClick('phone')"
        >
          <label for="phone" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
            Phone
            <span v-if="job.phoneRequirement === 'required'" class="text-danger-500">*</span>
            <span v-else class="text-surface-400 font-normal text-xs">(optional)</span>
          </label>
          <input
            id="phone"
            v-model="form.phone"
            type="tel"
            placeholder="+1 (555) 123-4567"
            autocomplete="tel"
            :tabindex="isPreview ? -1 : undefined"
            @input="emit('clear-error', 'phone')"
            :class="[
              'w-full rounded-xl border px-3.5 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors',
              errors.phone ? 'border-danger-300 dark:border-danger-700 focus:ring-danger-500 focus:border-danger-500' : 'border-surface-300 dark:border-surface-700',
              isPreview ? 'pointer-events-none' : '',
            ]"
          />
          <p v-if="errors.phone" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
            <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ errors.phone }}
          </p>
        </div>

        <!-- Resume / Cover Letter uploads -->
        <template v-if="job.requireResume || job.requireCoverLetter">
          <div class="border-t border-surface-100 dark:border-surface-800 pt-5 space-y-5">
            <!-- Resume -->
            <div
              v-if="job.requireResume"
              :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
              @click="onFieldClick('resume')"
            >
              <label for="resume" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                Resume / CV <span class="text-danger-500">*</span>
              </label>
              <div
                class="relative flex items-center gap-3 rounded-xl border border-dashed px-4 py-3 transition-colors"
                :class="errors.resume
                  ? 'border-danger-300 dark:border-danger-700 bg-danger-50/50 dark:bg-danger-950/20'
                  : 'border-surface-300 dark:border-surface-700 bg-surface-50 dark:bg-surface-800/50'
                "
              >
                <svg class="size-5 shrink-0 text-surface-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
                <div class="flex-1 min-w-0">
                  <p v-if="resume" class="text-sm text-surface-900 dark:text-surface-100 truncate">{{ resume.name }}</p>
                  <p v-else class="text-sm text-surface-500">PDF, DOC, or DOCX — max 10 MB</p>
                </div>
                <label
                  for="resume"
                  class="shrink-0 rounded-lg bg-white dark:bg-surface-700 border border-surface-200 dark:border-surface-600 px-3 py-1.5 text-xs font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-600 transition-colors"
                  :class="isPreview ? 'pointer-events-none' : 'cursor-pointer'"
                >
                  {{ resume ? 'Change' : 'Choose file' }}
                </label>
                <input
                  id="resume"
                  type="file"
                  accept=".pdf,.doc,.docx"
                  class="sr-only"
                  :disabled="isPreview"
                  @change="(e: Event) => { const t = e.target as HTMLInputElement; resume = t.files?.[0] ?? null; emit('clear-error', 'resume') }"
                />
              </div>
              <p v-if="errors.resume" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
                <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ errors.resume }}
              </p>
            </div>

            <!-- Cover Letter -->
            <div
              v-if="job.requireCoverLetter"
              :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
              @click="onFieldClick('coverLetter')"
            >
              <label for="coverLetterText" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                Cover Letter <span class="text-danger-500">*</span>
              </label>
              <textarea
                id="coverLetterText"
                v-model="coverLetter"
                rows="6"
                maxlength="10000"
                placeholder="Tell us why you're interested in this role…"
                :tabindex="isPreview ? -1 : undefined"
                :class="[
                  'w-full rounded-xl border px-4 py-3 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors',
                  errors.coverLetter ? 'border-danger-300 dark:border-danger-700' : 'border-surface-300 dark:border-surface-700',
                  isPreview ? 'pointer-events-none' : '',
                ]"
                @input="emit('clear-error', 'coverLetter')"
              />
              <p v-if="errors.coverLetter" class="mt-1.5 flex items-center gap-1 text-xs text-danger-600 dark:text-danger-400">
                <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ errors.coverLetter }}
              </p>
              <p v-else class="mt-1.5 text-xs text-surface-500">Max 10,000 characters.</p>
            </div>
          </div>
        </template>

        <!-- Custom questions -->
        <template v-if="job.questions && job.questions.length > 0">
          <div class="border-t border-surface-100 dark:border-surface-800 pt-5">
            <p class="text-sm font-medium text-surface-700 dark:text-surface-300 mb-4">Additional questions</p>
            <div class="space-y-5">
              <div
                v-for="q in job.questions"
                :key="q.id"
                :class="isPreview ? 'cursor-pointer rounded-xl ring-offset-2 ring-offset-white dark:ring-offset-surface-900 hover:ring-2 hover:ring-brand-300 dark:hover:ring-brand-700 transition-shadow' : ''"
                @click="onFieldClick(`question:${q.id}`)"
              >
                <div :class="isPreview ? 'pointer-events-none' : ''">
                  <DynamicField
                    v-model="responses[q.id]"
                    :question="q"
                    :error="errors[`q-${q.id}`]"
                    @file-selected="(id: string, file: File | null) => emit('file-selected', id, file)"
                  />
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- Submit row -->
        <div class="border-t border-surface-100 dark:border-surface-800 pt-5 flex flex-col sm:flex-row sm:items-center gap-3">
          <button
            type="submit"
            :disabled="isSubmitting || isPreview"
            :tabindex="isPreview ? -1 : undefined"
            class="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-7 py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            :class="isPreview ? 'pointer-events-none' : ''"
          >
            <!-- Spinner -->
            <svg
              v-if="isSubmitting"
              class="size-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ isSubmitting ? 'Submitting…' : 'Submit Application' }}
          </button>
          <p class="text-xs text-surface-400">Your information is kept confidential.</p>
        </div>
      </form>
    </div>
  </div>
</template>
