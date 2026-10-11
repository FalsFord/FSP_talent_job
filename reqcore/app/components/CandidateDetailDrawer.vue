<script setup lang="ts">
import { X, ExternalLink, Mail, Phone, Calendar, Clock, Briefcase, FileText, Plus, Download, Eye, AlertTriangle } from 'lucide-vue-next'
import { usePreviewReadOnly } from '~/composables/usePreviewReadOnly'

const props = defineProps<{
  candidateId: string
}>()

const emit = defineEmits<{
  close: []
}>()

const localePath = useLocalePath()
const { handlePreviewReadOnlyError } = usePreviewReadOnly()
const toast = useToast()

const { candidate, status: fetchStatus, error, refresh } = useCandidate(() => props.candidateId)
const { formatCandidateName, formatDate } = useOrgSettings()

// ─── Tabs ─────────────────────────────────────────────────────────────────────

const activeTab = ref<'applications' | 'documents'>('applications')

// ─── Apply to job modal ───────────────────────────────────────────────────────

const showApplyModal = ref(false)

function handleApplied() {
  showApplyModal.value = false
  refresh()
}

// ─── Interview scheduling ─────────────────────────────────────────────────────

const showInterviewSidebar = ref(false)
const interviewTargetApp = ref<{ id: string; jobTitle: string } | null>(null)

function openScheduleInterview(app: { id: string; job: { title: string } }) {
  interviewTargetApp.value = { id: app.id, jobTitle: app.job.title }
  showInterviewSidebar.value = true
}

// ─── Documents ────────────────────────────────────────────────────────────────

const { downloadDocument, getPreviewUrl } = useDocuments()

// Preview state
const showPreview = ref(false)
const previewUrl = ref<string | null>(null)
const previewFilename = ref('')
const previewMimeType = ref('')
const previewDocId = ref<string | null>(null)

const isPdfPreview = computed(() => previewMimeType.value === 'application/pdf')

async function handlePreview(docId: string, mimeType?: string) {
  if (mimeType && mimeType !== 'application/pdf') {
    await handleDownload(docId)
    return
  }
  showPreview.value = true
  previewDocId.value = docId
  const doc = candidate.value?.documents?.find((d: any) => d.id === docId)
  previewFilename.value = doc?.originalFilename ?? 'Document'
  previewMimeType.value = doc?.mimeType ?? 'application/pdf'
  previewUrl.value = getPreviewUrl(docId)
}

function closePreview() {
  showPreview.value = false
  previewUrl.value = null
  previewFilename.value = ''
  previewMimeType.value = ''
  previewDocId.value = null
}

async function handleDownload(docId: string) {
  try {
    await downloadDocument(docId)
  } catch {
    toast.error('Failed to download document')
  }
}

// ─── Display helpers ──────────────────────────────────────────────────────────

const applicationStatusClasses: Record<string, string> = {
  new: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-400',
  screening: 'bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-400',
  interview: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  offer: 'bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-400',
  hired: 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-400',
  rejected: 'bg-surface-100 text-surface-500 dark:bg-surface-800 dark:text-surface-400',
}

const genderLabels: Record<string, string> = {
  male: 'Male',
  female: 'Female',
  other: 'Other',
  prefer_not_to_say: 'Prefer not to say',
}

const documentTypeLabels: Record<string, string> = {
  resume: 'Resume',
  cover_letter: 'Cover Letter',
  other: 'Other',
}

function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ─── Body scroll lock + keyboard handling ─────────────────────────────────────

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <Transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        class="fixed inset-0 z-[55] bg-surface-900/40"
        @click="emit('close')"
      />
    </Transition>

    <!-- Panel -->
    <Transition
      enter-active-class="transition-transform duration-300 ease-out"
      leave-active-class="transition-transform duration-200 ease-in"
      enter-from-class="translate-x-full"
      leave-to-class="translate-x-full"
    >
      <aside
        class="fixed inset-y-0 right-0 z-[60] w-full max-w-2xl flex flex-col bg-white dark:bg-surface-900 shadow-2xl border-l border-surface-200 dark:border-surface-800"
        role="dialog"
        aria-modal="true"
        aria-label="Candidate detail"
      >
        <!-- Header -->
        <header class="flex items-center justify-between gap-3 px-5 py-4 border-b border-surface-200 dark:border-surface-800 shrink-0">
          <span class="text-sm font-semibold text-surface-900 dark:text-surface-100 truncate">Candidate Detail</span>
          <div class="flex items-center gap-2 shrink-0">
            <NuxtLink
              :to="localePath(`/dashboard/candidates/${candidateId}`)"
              class="inline-flex items-center gap-1.5 rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-1.5 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
            >
              <ExternalLink class="size-3.5" />
              Open full page
            </NuxtLink>
            <button
              class="rounded-lg p-1.5 text-surface-500 hover:text-surface-700 dark:hover:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
              @click="emit('close')"
            >
              <X class="size-4" />
            </button>
          </div>
        </header>

        <!-- Scrollable body -->
        <div class="flex-1 overflow-y-auto p-5 space-y-4">
          <!-- Loading -->
          <div v-if="fetchStatus === 'pending'" class="text-center py-12 text-surface-400">
            Loading candidate…
          </div>

          <!-- Error -->
          <div
            v-else-if="error"
            class="rounded-lg border border-danger-200 bg-danger-50 p-4 text-sm text-danger-700"
          >
            {{ error.statusCode === 404 ? 'Candidate not found.' : 'Failed to load candidate.' }}
          </div>

          <template v-else-if="candidate">
            <!-- Header -->
            <div class="min-w-0">
              <h2 class="text-2xl font-bold text-surface-900 dark:text-surface-50 truncate mb-1">
                {{ formatCandidateName(candidate) }}
              </h2>
              <div class="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 text-sm text-surface-500">
                <a
                  :href="`mailto:${candidate.email}`"
                  target="_blank"
                  class="inline-flex items-center gap-1 hover:text-brand-600 dark:hover:text-brand-400 hover:underline cursor-pointer transition-colors"
                >
                  <Mail class="size-3.5" />
                  {{ candidate.email }}
                </a>
                <span v-if="candidate.phone" class="inline-flex items-center gap-1">
                  <Phone class="size-3.5" />
                  {{ candidate.phone }}
                </span>
              </div>
            </div>

            <!-- Contact details -->
            <div class="rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-5">
              <h3 class="text-sm font-semibold text-surface-700 dark:text-surface-200 mb-3">Details</h3>
              <dl class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <dt class="text-surface-400">Email</dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">
                    <a
                      :href="`mailto:${candidate.email}`"
                      target="_blank"
                      class="hover:text-brand-600 dark:hover:text-brand-400 hover:underline cursor-pointer transition-colors"
                    >{{ candidate.email }}</a>
                  </dd>
                </div>
                <div>
                  <dt class="text-surface-400">Phone</dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">{{ candidate.phone || '—' }}</dd>
                </div>
                <div v-if="candidate.gender">
                  <dt class="text-surface-400">Gender</dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">
                    {{ genderLabels[candidate.gender] ?? candidate.gender }}
                  </dd>
                </div>
                <div v-if="candidate.dateOfBirth">
                  <dt class="text-surface-400">Date of Birth</dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">
                    {{ formatDate(candidate.dateOfBirth) }}
                  </dd>
                </div>
                <div v-if="candidate.displayName">
                  <dt class="text-surface-400">Display Name</dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">{{ candidate.displayName }}</dd>
                </div>
                <div>
                  <dt class="text-surface-400 inline-flex items-center gap-1">
                    <Calendar class="size-3.5" />
                    Created
                  </dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">
                    <TimelineDateLink :date="candidate.createdAt">{{ new Date(candidate.createdAt).toLocaleDateString() }}</TimelineDateLink>
                  </dd>
                </div>
                <div>
                  <dt class="text-surface-400 inline-flex items-center gap-1">
                    <Clock class="size-3.5" />
                    Updated
                  </dt>
                  <dd class="text-surface-700 dark:text-surface-200 font-medium">
                    <TimelineDateLink :date="candidate.updatedAt">{{ new Date(candidate.updatedAt).toLocaleDateString() }}</TimelineDateLink>
                  </dd>
                </div>
              </dl>
            </div>

            <!-- Properties -->
            <div class="rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-4">
              <h3 class="text-sm font-semibold text-surface-700 dark:text-surface-200 mb-2 px-2">Properties</h3>
              <PropertyBlock
                entity-type="candidate"
                :entity-id="candidateId"
                :entries="(candidate.properties ?? []) as import('~~/shared/properties').PropertyEntry[]"
                @refresh="refresh()"
              />
            </div>

            <!-- Tabs -->
            <div class="border-b border-surface-200 dark:border-surface-800">
              <div class="flex gap-1">
                <button
                  class="cursor-pointer px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
                  :class="activeTab === 'applications'
                    ? 'border-brand-600 text-brand-600'
                    : 'border-transparent text-surface-500 hover:text-surface-700 hover:border-surface-300 dark:hover:text-surface-300'"
                  @click="activeTab = 'applications'"
                >
                  Applications ({{ candidate.applications?.length ?? 0 }})
                </button>
                <button
                  class="cursor-pointer px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
                  :class="activeTab === 'documents'
                    ? 'border-brand-600 text-brand-600'
                    : 'border-transparent text-surface-500 hover:text-surface-700 hover:border-surface-300 dark:hover:text-surface-300'"
                  @click="activeTab = 'documents'"
                >
                  Documents ({{ candidate.documents?.length ?? 0 }})
                </button>
              </div>
            </div>

            <!-- Applications tab -->
            <div v-if="activeTab === 'applications'">
              <div class="flex justify-end mb-3">
                <button
                  class="inline-flex items-center gap-1.5 rounded-lg border border-surface-300 dark:border-surface-600 px-3 py-1.5 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                  @click="showApplyModal = true"
                >
                  <Plus class="size-3.5" />
                  Apply to Job
                </button>
              </div>

              <div
                v-if="!candidate.applications?.length"
                class="rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-8 text-center"
              >
                <Briefcase class="size-8 text-surface-300 dark:text-surface-600 mx-auto mb-2" />
                <p class="text-sm text-surface-500 dark:text-surface-400">No applications yet.</p>
              </div>

              <div v-else class="space-y-2">
                <div
                  v-for="app in candidate.applications"
                  :key="app.id"
                  class="flex flex-col sm:flex-row sm:items-center sm:justify-between rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 px-4 py-3 hover:border-surface-300 dark:hover:border-surface-700 hover:shadow-sm transition-all group gap-2"
                >
                  <NuxtLink
                    :to="localePath(`/dashboard/applications/${app.id}`)"
                    class="min-w-0 flex-1 block"
                  >
                    <h4 class="text-sm font-semibold text-surface-900 dark:text-surface-100 group-hover:text-brand-600 transition-colors truncate">
                      {{ app.job.title }}
                    </h4>
                    <span class="text-xs text-surface-400">
                      Applied <TimelineDateLink :date="app.createdAt">{{ new Date(app.createdAt).toLocaleDateString() }}</TimelineDateLink>
                    </span>
                  </NuxtLink>
                  <div class="flex items-center gap-2 shrink-0 sm:ml-3">
                    <button
                      class="inline-flex items-center gap-1 rounded-lg border border-surface-200 dark:border-surface-700 px-2 py-1 text-xs font-medium text-surface-600 dark:text-surface-400 hover:border-brand-400 dark:hover:border-brand-600 hover:bg-brand-50 dark:hover:bg-brand-950/30 hover:text-brand-700 dark:hover:text-brand-300 transition-all cursor-pointer"
                      title="Schedule Interview"
                      @click="openScheduleInterview(app)"
                    >
                      <Calendar class="size-3" />
                      Schedule
                    </button>
                    <span
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0"
                      :class="applicationStatusClasses[app.status] ?? 'bg-surface-100 text-surface-600'"
                    >
                      {{ app.status }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Documents tab -->
            <div v-if="activeTab === 'documents'">
              <!-- Inline PDF preview -->
              <template v-if="showPreview">
                <div class="flex items-center justify-between mb-3">
                  <button
                    class="inline-flex items-center gap-1.5 text-sm font-medium text-surface-600 dark:text-surface-300 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                    @click="closePreview"
                  >
                    ← Back to documents
                  </button>
                  <div class="flex items-center gap-1">
                    <button
                      v-if="previewDocId"
                      class="rounded-lg p-1.5 text-surface-400 hover:text-brand-600 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                      title="Download"
                      @click="handleDownload(previewDocId!)"
                    >
                      <Download class="size-4" />
                    </button>
                  </div>
                </div>

                <div v-if="previewFilename" class="flex items-center gap-2 mb-3">
                  <FileText class="size-4 text-surface-400 shrink-0" />
                  <span class="text-sm font-medium text-surface-700 dark:text-surface-200 truncate">
                    {{ previewFilename }}
                  </span>
                </div>

                <iframe
                  v-if="previewUrl && isPdfPreview"
                  :src="previewUrl"
                  class="w-full rounded-lg border border-surface-200 dark:border-surface-800"
                  style="height: 60vh;"
                  title="Document preview"
                />
              </template>

              <!-- Document list -->
              <template v-else>
                <div
                  v-if="!candidate.documents?.length"
                  class="rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-8 text-center"
                >
                  <FileText class="size-8 text-surface-300 dark:text-surface-600 mx-auto mb-2" />
                  <p class="text-sm text-surface-500 dark:text-surface-400">No documents yet.</p>
                </div>

                <div v-else class="space-y-2">
                  <div
                    v-for="doc in candidate.documents"
                    :key="doc.id"
                    class="group flex items-center justify-between rounded-lg border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 px-4 py-3 transition-colors"
                    :class="doc.mimeType === 'application/pdf' ? 'cursor-pointer hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-950/30' : ''"
                    @click="doc.mimeType === 'application/pdf' ? handlePreview(doc.id, doc.mimeType) : undefined"
                  >
                    <div class="flex items-center gap-3 min-w-0">
                      <FileText class="size-4 shrink-0" :class="doc.mimeType === 'application/pdf' ? 'text-danger-500 dark:text-danger-400' : 'text-surface-400'" />
                      <div class="min-w-0">
                        <p class="text-sm font-medium text-surface-700 dark:text-surface-200 truncate">
                          {{ doc.originalFilename }}
                        </p>
                        <span class="text-xs text-surface-400">
                          {{ documentTypeLabels[doc.type] ?? doc.type }}
                          · <TimelineDateLink :date="doc.createdAt">{{ new Date(doc.createdAt).toLocaleDateString() }}</TimelineDateLink>
                          <template v-if="doc.mimeType === 'application/pdf'"> · <span class="text-brand-500 dark:text-brand-400">Click to preview</span></template>
                        </span>
                      </div>
                    </div>
                    <div class="flex items-center gap-1 shrink-0" @click.stop>
                      <button
                        v-if="doc.mimeType === 'application/pdf'"
                        class="rounded-lg p-1.5 text-surface-400 hover:text-brand-600 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="Preview PDF"
                        @click="handlePreview(doc.id, doc.mimeType)"
                      >
                        <Eye class="size-4" />
                      </button>
                      <button
                        class="rounded-lg p-1.5 text-surface-400 hover:text-brand-600 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="Download"
                        @click="handleDownload(doc.id)"
                      >
                        <Download class="size-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </template>
        </div>
      </aside>
    </Transition>

    <!-- Apply to Job Modal -->
    <ApplyToJobModal
      v-if="showApplyModal && candidate"
      :candidate-id="candidateId"
      @close="showApplyModal = false"
      @created="handleApplied"
    />

    <!-- Interview Schedule Sidebar -->
    <InterviewScheduleSidebar
      v-if="showInterviewSidebar && interviewTargetApp && candidate"
      :application-id="interviewTargetApp.id"
      :candidate-name="`${candidate.firstName} ${candidate.lastName}`"
      :job-title="interviewTargetApp.jobTitle"
      @close="showInterviewSidebar = false"
      @scheduled="showInterviewSidebar = false"
    />
  </Teleport>
</template>
