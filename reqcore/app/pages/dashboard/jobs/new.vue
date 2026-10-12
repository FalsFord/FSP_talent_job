<script setup lang="ts">
import {
  ArrowLeft,
  Check,
  Plus,
  Trash2,
  ChevronRight,
  ArrowRight,
  Link2,
  Rocket,
  FileEdit,
  ExternalLink,
  PartyPopper,
  Copy,
  Eye,
  Briefcase,
  FileText,
  MessageSquare,
  Brain,
  Sparkles,
  Loader2,
  SlidersHorizontal,
  Share2,
  Globe,
  Mail,
  Users,
  BarChart3,
  Hash,
  Megaphone,
  Building2,
  Search,
} from 'lucide-vue-next'
import { z } from 'zod'

definePageMeta({
  layout: 'dashboard',
  middleware: ['auth', 'require-org'],
  fullbleed: true,
})

useSeoMeta({
  title: 'Create Job — Reqcore',
  description: 'Create a new job posting',
})

const localePath = useLocalePath()
const { createJob } = useJobs()
const { track } = useTrack()
const toast = useToast()

type QuestionType =
  | 'short_text'
  | 'long_text'
  | 'single_select'
  | 'multi_select'
  | 'number'
  | 'date'
  | 'url'
  | 'checkbox'
  | 'file_upload'

type DraftQuestion = {
  id: string
  label: string
  type: QuestionType
  description?: string | null
  required: boolean
  options?: string[] | null
}

// Wizard state
const currentStep = ref<1 | 2 | 3 | 4>(1)
const wizardEditor = useTemplateRef<HTMLElement>('wizardEditor')
const steps = [
  { id: 1, title: 'Job details', description: 'Tell applicants about this role.' },
  { id: 2, title: 'Application form', description: 'Design the application form.' },
  { id: 3, title: 'AI scoring criteria', description: 'Define how AI evaluates candidates.' },
  { id: 4, title: 'Publish & distribute', description: 'Go live and share across job boards.' },
]

// Step 1: Job details (API-supported fields)
const form = ref({
  title: '',
  description: '',
  location: '',
  type: 'full_time' as 'full_time' | 'part_time' | 'contract' | 'internship',
  experienceLevel: 'mid' as 'junior' | 'mid' | 'senior' | 'lead',
  remoteStatus: undefined as 'remote' | 'hybrid' | 'onsite' | undefined,
})

// Step 2: Application form (client-only for now)
const applicationForm = ref({
  phoneRequirement: 'optional' as 'hidden' | 'optional' | 'required',
  requireResume: true,
  requireCoverLetter: false,
  questions: [] as DraftQuestion[],
})

// Step 3: AI scoring criteria
type ScoringCriterionDraft = {
  key: string
  name: string
  description: string
  category: 'technical' | 'experience' | 'soft_skills' | 'education' | 'culture' | 'custom'
  maxScore: number
  weight: number
}
const scoringCriteria = ref<ScoringCriterionDraft[]>([])
const scoringMode = ref<'none' | 'premade' | 'ai' | 'custom'>('none')
const selectedTemplate = ref<'standard' | 'technical' | 'non_technical'>('standard')
const isGeneratingCriteria = ref(false)
const showCustomForm = ref(false)
const showAdvanced = ref(false)
const editingCriterion = ref<ScoringCriterionDraft | null>(null)
const autoScoreOnApply = ref(false)

const customCriterionForm = ref({
  key: '',
  name: '',
  description: '',
  category: 'custom' as ScoringCriterionDraft['category'],
  maxScore: 10,
  weight: 50,
})

const categoryLabels: Record<string, string> = {
  technical: 'Technical',
  experience: 'Experience',
  soft_skills: 'Soft Skills',
  education: 'Education',
  culture: 'Culture',
  custom: 'Custom',
}

const categoryColorClasses: Record<string, string> = {
  technical: 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:ring-blue-800',
  experience: 'bg-purple-50 text-purple-700 ring-purple-200 dark:bg-purple-950/50 dark:text-purple-300 dark:ring-purple-800',
  soft_skills: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:ring-amber-800',
  education: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-800',
  culture: 'bg-pink-50 text-pink-700 ring-pink-200 dark:bg-pink-950/50 dark:text-pink-300 dark:ring-pink-800',
  custom: 'bg-surface-50 text-surface-700 ring-surface-200 dark:bg-surface-800/50 dark:text-surface-300 dark:ring-surface-700',
}

// Pre-made scoring templates (no API call needed)
const scoringTemplates: Record<'standard' | 'technical' | 'non_technical', ScoringCriterionDraft[]> = {
  standard: [
    { key: 'technical_skills', name: 'Technical Skills', description: 'Evaluate the candidate\'s technical competencies against the job requirements.', category: 'technical', maxScore: 10, weight: 50 },
    { key: 'relevant_experience', name: 'Relevant Experience', description: 'Assess years and quality of experience directly relevant to the role.', category: 'experience', maxScore: 10, weight: 50 },
    { key: 'education_fit', name: 'Education & Certifications', description: 'Evaluate educational background and certifications relevant to the position.', category: 'education', maxScore: 10, weight: 30 },
  ],
  technical: [
    { key: 'core_tech_stack', name: 'Core Tech Stack Match', description: 'How well the candidate\'s technical skills match the primary technologies.', category: 'technical', maxScore: 10, weight: 70 },
    { key: 'system_design', name: 'System Design & Architecture', description: 'Evidence of system design experience and architectural decision-making.', category: 'technical', maxScore: 10, weight: 50 },
    { key: 'engineering_practices', name: 'Engineering Practices', description: 'Testing, CI/CD, code review, and software development lifecycle experience.', category: 'technical', maxScore: 10, weight: 40 },
    { key: 'relevant_experience', name: 'Relevant Experience', description: 'Years and depth of experience in similar roles or domains.', category: 'experience', maxScore: 10, weight: 50 },
    { key: 'leadership_collab', name: 'Leadership & Collaboration', description: 'Evidence of mentoring, tech leadership, and cross-team collaboration.', category: 'soft_skills', maxScore: 10, weight: 30 },
  ],
  non_technical: [
    { key: 'relevant_experience', name: 'Relevant Experience', description: 'Depth and breadth of experience applicable to the role.', category: 'experience', maxScore: 10, weight: 60 },
    { key: 'communication', name: 'Communication Skills', description: 'Evidence of written and verbal communication ability.', category: 'soft_skills', maxScore: 10, weight: 50 },
    { key: 'domain_knowledge', name: 'Domain Knowledge', description: 'Relevant industry or domain expertise.', category: 'experience', maxScore: 10, weight: 40 },
    { key: 'education_fit', name: 'Education & Certifications', description: 'Educational background and certifications relevant to the position.', category: 'education', maxScore: 10, weight: 30 },
    { key: 'culture_fit', name: 'Culture & Values Alignment', description: 'Indicators of alignment with company values and team culture.', category: 'culture', maxScore: 10, weight: 30 },
  ],
}

// Recommend a template from the job title so the default path needs zero decisions.
const TECHNICAL_TITLE_RE = /\b(engineer|developer|programmer|software|data|devops|back[\s-]?end|front[\s-]?end|full[\s-]?stack|sysadmin|sre|architect|scientist|machine learning|ml|ai|qa|security|cloud|infrastructure)\b/i
const recommendedTemplate = computed<'standard' | 'technical' | 'non_technical'>(() =>
  TECHNICAL_TITLE_RE.test(form.value.title) ? 'technical' : 'standard',
)
const recommendedCriteria = computed(() => scoringTemplates[recommendedTemplate.value])

function loadPremadeCriteria(template: 'standard' | 'technical' | 'non_technical') {
  // Clone so per-job weight edits never mutate the shared template objects.
  scoringCriteria.value = scoringTemplates[template].map(c => ({ ...c }))
  scoringMode.value = 'premade'
}

function useRecommendedScoring() {
  selectedTemplate.value = recommendedTemplate.value
  loadPremadeCriteria(recommendedTemplate.value)
}

function skipScoring() {
  scoringCriteria.value = []
  scoringMode.value = 'none'
  showAdvanced.value = false
  nextStep()
}

async function generateAiCriteria() {
  if (!form.value.title) {
    toast.warning('Job title required', 'Add a job title in Step 1 first so AI can generate relevant criteria.')
    return
  }
  if (!form.value.description) {
    toast.warning('Job description required', 'Add a job description in Step 1 first so AI can generate relevant criteria.')
    return
  }
  isGeneratingCriteria.value = true
  try {
    const result = await $fetch('/api/ai-config/generate-criteria', {
      method: 'POST',
      body: {
        title: form.value.title,
        description: form.value.description,
      },
    })
    scoringCriteria.value = (result.criteria ?? []).map((c: any) => ({
      key: c.key,
      name: c.name,
      description: c.description ?? '',
      category: c.category ?? 'custom',
      maxScore: c.maxScore ?? 10,
      weight: c.weight ?? 50,
    }))
    scoringMode.value = 'ai'
    toast.success('Criteria generated', `${scoringCriteria.value.length} scoring criteria created from job description.`)
  } catch (err: any) {
    const statusCode = err?.data?.statusCode ?? err?.statusCode
    const statusMessage = err?.data?.statusMessage ?? ''
    if (statusCode === 422 && statusMessage.includes('AI provider not configured')) {
      toast.add({
        type: 'warning',
        title: 'AI provider not configured',
        message: 'Set up your AI provider and model before generating criteria.',
        link: { label: 'Go to AI Settings', href: '/dashboard/settings/ai' },
        duration: 10000,
      })
    } else {
      toast.error('Failed to generate criteria', {
        message: 'Could not generate criteria. Make sure your AI provider is configured in Settings → AI, then try again.',
        details: statusMessage || `${statusCode ?? 'Unknown'} error — no additional details from server.`,
        statusCode,
      })
    }
  } finally {
    isGeneratingCriteria.value = false
  }
}

function addCustomCriterion() {
  const f = customCriterionForm.value
  if (scoringCriteria.value.length >= 20) {
    toast.warning('Criteria limit reached', 'You can add up to 20 scoring criteria.')
    return
  }

  const parsed = scoringCriterionDraftSchema.safeParse({
    ...f,
    key: f.key.trim(),
    name: f.name.trim(),
    description: f.description.trim(),
  })
  if (!parsed.success) {
    toast.warning('Invalid criterion', parsed.error.issues[0]?.message ?? 'Check the criterion fields and try again.')
    return
  }

  const keyExists = scoringCriteria.value.some(c => c.key === parsed.data.key)
  if (keyExists) {
    toast.warning('Duplicate criterion', `A criterion with key "${parsed.data.key}" already exists.`)
    return
  }

  scoringCriteria.value.push(parsed.data)
  customCriterionForm.value = { key: '', name: '', description: '', category: 'custom', maxScore: 10, weight: 50 }
  showCustomForm.value = false
  if (scoringMode.value === 'none') scoringMode.value = 'custom'
}

function removeCriterion(key: string) {
  scoringCriteria.value = scoringCriteria.value.filter(c => c.key !== key)
}

function autoGenerateKey(name: string): string {
  return name.toLowerCase().trim()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, '_')
    .slice(0, 50)
}

const isSubmitting = ref(false)
const errors = ref<Record<string, string>>({})
const linkCopied = ref(false)

const formSchema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200, 'Title must be 200 characters or less'),
  description: z.string().trim().max(100_000, 'Description is too long'),
  location: z.string().trim().max(500, 'Location must be 500 characters or less'),
  type: z.enum(['full_time', 'part_time', 'contract', 'internship']),
  experienceLevel: z.enum(['junior', 'mid', 'senior', 'lead']),
  remoteStatus: z.enum(['remote', 'hybrid', 'onsite']).optional(),
})

const draftQuestionSchema = z.object({
  id: z.string().min(1),
  label: z.string().trim().min(1).max(500),
  type: z.enum(['short_text', 'long_text', 'single_select', 'multi_select', 'number', 'date', 'url', 'checkbox', 'file_upload']),
  description: z.string().trim().max(1000).nullish(),
  required: z.boolean(),
  options: z.array(z.string().trim().min(1).max(200)).max(50).nullish(),
})

const applicationFormSchema = z.object({
  phoneRequirement: z.enum(['hidden', 'optional', 'required']),
  requireResume: z.boolean(),
  requireCoverLetter: z.boolean(),
  questions: z.array(draftQuestionSchema).max(50),
})

const scoringCriterionDraftSchema = z.object({
  key: z.string().trim().min(1).max(100).regex(/^[a-z][a-z0-9_]*$/),
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000),
  category: z.enum(['technical', 'experience', 'soft_skills', 'education', 'culture', 'custom']),
  maxScore: z.number().int().min(1).max(100),
  weight: z.number().int().min(0).max(100),
})

// Check if at least one AI provider is configured with a valid API key.
// /api/ai-config returns an array of configurations now (multi-config era).
interface AiConfigCheckRow { hasApiKey: boolean }
const { data: aiConfigData } = useFetch<AiConfigCheckRow[]>('/api/ai-config', { key: 'ai-config-check', headers: useRequestHeaders(['cookie']) })
const isAiConfigured = computed(() => {
  return Array.isArray(aiConfigData.value) && aiConfigData.value.some((c) => c.hasApiKey)
})

// Auto-save to localStorage
const AUTO_SAVE_KEY = 'reqcore-job-draft'

function saveFormToStorage() {
  if (!import.meta.client) return
  try {
    const data = {
      form: form.value,
      applicationForm: applicationForm.value,
      scoringCriteria: scoringCriteria.value,
      scoringMode: scoringMode.value,
      autoScoreOnApply: autoScoreOnApply.value,
      currentStep: currentStep.value,
    }
    localStorage.setItem(AUTO_SAVE_KEY, JSON.stringify(data))
  } catch { /* storage full or unavailable */ }
}

function openDraftPreview() {
  saveFormToStorage()
  window.open(localePath('/dashboard/jobs/preview'), '_blank', 'noopener,noreferrer')
}

function restoreFormFromStorage() {
  if (!import.meta.client) return
  try {
    const raw = localStorage.getItem(AUTO_SAVE_KEY)
    if (!raw) return
    const data = z.object({
      form: z.unknown().optional(),
      applicationForm: z.unknown().optional(),
      scoringCriteria: z.unknown().optional(),
      scoringMode: z.unknown().optional(),
      autoScoreOnApply: z.unknown().optional(),
      currentStep: z.unknown().optional(),
    }).parse(JSON.parse(raw))

    const storedForm = formSchema.safeParse(data.form)
    if (storedForm.success) {
      form.value = {
        ...storedForm.data,
        remoteStatus: storedForm.data.remoteStatus,
      }
    }

    const storedApplicationForm = applicationFormSchema.safeParse(data.applicationForm)
    if (storedApplicationForm.success) applicationForm.value = storedApplicationForm.data

    const storedCriteria = z.array(scoringCriterionDraftSchema).max(20).safeParse(data.scoringCriteria)
    if (storedCriteria.success) scoringCriteria.value = storedCriteria.data

    const storedMode = z.enum(['none', 'premade', 'ai', 'custom']).safeParse(data.scoringMode)
    if (storedMode.success) scoringMode.value = storedMode.data

    const storedAutoScore = z.boolean().safeParse(data.autoScoreOnApply)
    if (storedAutoScore.success) autoScoreOnApply.value = storedAutoScore.data

    const storedStep = z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).safeParse(data.currentStep)
    currentStep.value = storedStep.success && storedForm.success ? storedStep.data : 1
  } catch { /* corrupted data, ignore */ }
}

function clearFormStorage() {
  if (!import.meta.client) return
  try { localStorage.removeItem(AUTO_SAVE_KEY) } catch { /* ignore */ }
}

onMounted(() => {
  restoreFormFromStorage()
})

// Reset all wizard state to initial values (called when user clicks "New Job" again)
function resetState() {
  currentStep.value = 1
  form.value = {
    title: '',
    description: '',
    location: '',
    type: 'full_time',
    experienceLevel: 'mid',
    remoteStatus: undefined,
  }
  applicationForm.value = {
    phoneRequirement: 'optional',
    requireResume: true,
    requireCoverLetter: false,
    questions: [],
  }
  scoringCriteria.value = []
  scoringMode.value = 'none'
  autoScoreOnApply.value = false
  isPublished.value = false
  createdJobId.value = ''
  createdJobSlug.value = ''
  finalApplicationLink.value = ''
  errors.value = {}
  createdLinks.value = {}
  customBoardLinks.value = []
  clearFormStorage()
}

// Shared signal incremented by AppTopBar when the user is already on this page
const newJobResetSignal = useState('new-job-reset-signal', () => 0)
watch(newJobResetSignal, (next, prev) => {
  if (next > prev) resetState()
})

// Auto-save when step changes or form data changes
watch([currentStep, form, applicationForm, scoringCriteria, scoringMode, autoScoreOnApply], () => {
  saveFormToStorage()
}, { deep: true })


// Step 4: Publish & Distribute
const publishChoice = ref<'publish' | 'draft'>('publish')
const isPublished = ref(false)
const createdJobSlug = ref('')
const createdJobId = ref('')
const finalApplicationLink = ref('')
const linkCopiedFinal = ref(false)

// Distribution channels for quick tracking link creation
const distributionGroups = [
  { key: 'job_board', label: 'Job boards' },
  { key: 'outreach', label: 'Direct outreach' },
  { key: 'social', label: 'Social media' },
] as const

const distributionChannels = [
  { channel: 'linkedin', name: 'LinkedIn', description: 'Post on LinkedIn Jobs or share in your feed', category: 'job_board' },
  { channel: 'indeed', name: 'Indeed', description: 'List on the Indeed job board', category: 'job_board' },
  { channel: 'glassdoor', name: 'Glassdoor', description: 'Publish on Glassdoor listings', category: 'job_board' },
  { channel: 'ziprecruiter', name: 'ZipRecruiter', description: 'Post on ZipRecruiter', category: 'job_board' },
  { channel: 'email', name: 'Email campaign', description: 'Send to candidates or mailing list', category: 'outreach' },
  { channel: 'referral', name: 'Employee referral', description: 'Share internally with your team', category: 'outreach' },
  { channel: 'career_site', name: 'Career site', description: 'Embed on your company website', category: 'outreach' },
  { channel: 'twitter', name: 'X (Twitter)', description: 'Share on your X timeline', category: 'social' },
  { channel: 'facebook', name: 'Facebook', description: 'Post on Facebook page or groups', category: 'social' },
  { channel: 'reddit', name: 'Reddit', description: 'Share in relevant subreddits', category: 'social' },
] as const

const channelIcons: Record<string, any> = {
  linkedin: Briefcase,
  indeed: Search,
  glassdoor: Building2,
  ziprecruiter: Megaphone,
  email: Mail,
  referral: Users,
  career_site: Globe,
  twitter: Hash,
  facebook: Users,
  reddit: MessageSquare,
}

// Track created distribution links: channel → { code, url, loading, copied }
const createdLinks = ref<Record<string, { code: string; url: string; loading: boolean; copied: boolean }>>({})

async function createChannelLink(channel: string, channelName: string) {
  if (createdLinks.value[channel]?.code) return
  createdLinks.value[channel] = { code: '', url: '', loading: true, copied: false }
  try {
    const result = await $fetch<{ id: string; code: string }>('/api/tracking-links', {
      method: 'POST',
      body: {
        jobId: createdJobId.value,
        channel,
        name: `${form.value.title} — ${channelName}`,
      },
    })
    const base = `${requestUrl.protocol}//${requestUrl.host}`
    const trackUrl = `${base}/api/public/track/${encodeURIComponent(result.code)}`
    createdLinks.value[channel] = { code: result.code, url: trackUrl, loading: false, copied: false }
    track('tracking_link_created', { channel, source: 'job_wizard' })
  } catch {
    delete createdLinks.value[channel]
    toast.error(`Failed to create tracking link for ${channelName}`)
  }
}

async function copyChannelLink(channel: string) {
  const link = createdLinks.value[channel]
  if (!link?.url) return
  try {
    await navigator.clipboard.writeText(link.url)
    link.copied = true
    setTimeout(() => { link.copied = false }, 2500)
  } catch {
    toast.info(link.url)
  }
}

const createdLinkCount = computed(() =>
  Object.values(createdLinks.value).filter(l => l.code).length + customBoardLinks.value.length
)

// Custom job board links
const customBoardName = ref('')
const customBoardLinks = ref<Array<{ id: string; name: string; channel: string; code: string; url: string; copied: boolean }>>([])
const isCreatingCustomBoard = ref(false)

async function createCustomBoardLink() {
  const name = customBoardName.value.trim()
  if (!name) return
  // Use a slug derived from the custom board name for local dedup only
  const dedupeKey = `custom_${name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 50)}`

  // Prevent duplicates
  if (customBoardLinks.value.some(l => l.channel === dedupeKey)) {
    toast.warning('Duplicate board', `A custom link for "${name}" already exists.`)
    return
  }

  isCreatingCustomBoard.value = true
  try {
    const result = await $fetch<{ id: string; code: string }>('/api/tracking-links', {
      method: 'POST',
      body: {
        jobId: createdJobId.value,
        channel: 'custom',
        name: `${form.value.title} — ${name}`,
      },
    })
    const base = `${requestUrl.protocol}//${requestUrl.host}`
    const trackUrl = `${base}/api/public/track/${encodeURIComponent(result.code)}`
    customBoardLinks.value.push({ id: result.id, name, channel: dedupeKey, code: result.code, url: trackUrl, copied: false })
    customBoardName.value = ''
    track('tracking_link_created', { channel: 'custom', customName: name, source: 'job_wizard_custom' })
  } catch {
    toast.error(`Failed to create tracking link for "${name}"`)
  } finally {
    isCreatingCustomBoard.value = false
  }
}

async function copyCustomBoardLink(index: number) {
  const link = customBoardLinks.value[index]
  if (!link?.url) return
  try {
    await navigator.clipboard.writeText(link.url)
    link.copied = true
    setTimeout(() => { link.copied = false }, 2500)
  } catch {
    toast.info(link.url)
  }
}

function validateStep1(): boolean {
  const result = formSchema.safeParse(form.value)
  if (!result.success) {
    errors.value = {}
    for (const issue of result.error.issues) {
      const field = issue.path[0]?.toString()
      if (field) errors.value[field] = issue.message
    }
    return false
  }
  errors.value = {}
  return true
}

// Pure check with no side-effects so it never populates errors on its own
const isStep1Valid = computed(() => formSchema.safeParse(form.value).success)

const canGoNext = computed(() => {
  if (currentStep.value === 1) return isStep1Valid.value
  return true
})

function goToStep(step: 1 | 2 | 3 | 4) {
  if (step === currentStep.value) return
  // Validate step 1 before leaving it
  if (currentStep.value === 1 && step > 1 && !validateStep1()) return
  currentStep.value = step
}

function nextStep() {
  if (currentStep.value < 4) {
    if (currentStep.value === 1 && !validateStep1()) return
    currentStep.value++
  }
}

function prevStep() {
  if (currentStep.value > 1) currentStep.value--
}

watch(currentStep, async () => {
  await nextTick()
  wizardEditor.value?.scrollTo({ top: 0, behavior: 'auto' })
})

function slugifyTitle(raw: string) {
  return raw
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60)
}

const requestUrl = useRequestURL()
const applicationLink = computed(() => {
  const base = `${requestUrl.protocol}//${requestUrl.host}`
  const slugBase = slugifyTitle(form.value.title) || 'new-job'
  return `${base}/jobs/${slugBase}-xxxxxxxx/apply`
})

async function copyApplicationLink() {
  try {
    await navigator.clipboard.writeText(applicationLink.value)
    linkCopied.value = true
    setTimeout(() => {
      linkCopied.value = false
    }, 2000)
  } catch {
    // ignore clipboard issues silently
  }
}

async function handleSubmit(mode: 'publish' | 'draft' = publishChoice.value) {
  if (isSubmitting.value) return

  // Ensure step 1 is valid before submit
  if (!validateStep1()) {
    currentStep.value = 1
    return
  }

  const normalizedForm = formSchema.parse(form.value)
  isSubmitting.value = true
  try {
    const created = await createJob({
      title: normalizedForm.title,
      description: normalizedForm.description || undefined,
      location: normalizedForm.location || undefined,
      type: normalizedForm.type,
      experienceLevel: normalizedForm.experienceLevel,
      remoteStatus: normalizedForm.remoteStatus,
      phoneRequirement: applicationForm.value.phoneRequirement,
      requireResume: applicationForm.value.requireResume,
      requireCoverLetter: applicationForm.value.requireCoverLetter,
      autoScoreOnApply: scoringCriteria.value.length > 0 && autoScoreOnApply.value,
      status: mode === 'publish' ? 'open' : 'draft',
      questions: applicationForm.value.questions.map((question, index) => ({
        label: question.label,
        type: question.type,
        description: question.description || undefined,
        required: question.required,
        options: question.options || undefined,
        displayOrder: index,
      })),
      criteria: scoringCriteria.value.map((criterion, index) => ({
        key: criterion.key,
        name: criterion.name,
        description: criterion.description || undefined,
        category: criterion.category,
        maxScore: criterion.maxScore,
        weight: criterion.weight,
        displayOrder: index,
      })),
    })

    track('job_created')

    if (mode === 'publish' && created?.id) {
      // Build the real application link
      const base = `${requestUrl.protocol}//${requestUrl.host}`
      const slug = created.slug || created.id
      finalApplicationLink.value = `${base}/jobs/${slug}/apply`
      createdJobSlug.value = slug
      createdJobId.value = created.id

      track('job_published')

      // Auto-copy to clipboard
      try {
        await navigator.clipboard.writeText(finalApplicationLink.value)
        linkCopiedFinal.value = true
        setTimeout(() => { linkCopiedFinal.value = false }, 3000)
      } catch {
        // Clipboard may not be available
      }

      isPublished.value = true
    } else {
      // Saved as draft — go to jobs list
      await navigateTo(localePath('/dashboard/jobs'))
    }
    clearFormStorage()
  } catch (err: any) {
    const statusMessage = err?.data?.statusMessage ?? 'Something went wrong while creating the job.'
    toast.error('Failed to create job', {
      message: statusMessage,
      statusCode: err?.data?.statusCode,
    })
  } finally {
    isSubmitting.value = false
  }
}

async function copyFinalLink() {
  try {
    await navigator.clipboard.writeText(finalApplicationLink.value)
    linkCopiedFinal.value = true
    setTimeout(() => { linkCopiedFinal.value = false }, 3000)
  } catch {
    // fallback: show the link so the user can copy manually
    toast.info(finalApplicationLink.value)
  }
}

const typeOptions = [
  { value: 'full_time', label: 'Full-time' },
  { value: 'part_time', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
  { value: 'internship', label: 'Internship' },
]
</script>

<template>
  <div class="mx-auto flex h-full w-full max-w-7xl flex-col overflow-y-auto px-4 py-2 sm:px-6 lg:px-8 lg:py-3 xl:min-h-0 xl:overflow-hidden">
    <!-- Compact wizard navigation -->
    <div class="mb-3 flex items-center gap-3">
      <NuxtLink
        :to="$localePath('/dashboard/jobs')"
        class="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-800 dark:text-surface-400 dark:hover:bg-surface-800 dark:hover:text-surface-100"
      >
        <ArrowLeft class="size-3.5" />
        <span class="hidden sm:inline">Jobs</span>
      </NuxtLink>

      <ol class="flex min-w-0 flex-1 items-center gap-1">
        <li
          v-for="(step, idx) in steps"
          :key="step.id"
          class="flex items-center flex-1 min-w-0 cursor-pointer"
          @click="goToStep(step.id as typeof currentStep)"
        >
          <div class="flex min-w-0 items-center gap-1.5">
            <div
              class="flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium transition-all"
              :class="[
                currentStep === step.id
                  ? 'bg-brand-600 text-white border-brand-600 ring-1 ring-brand-100 dark:ring-brand-950'
                  : currentStep > step.id
                    ? 'bg-brand-100 dark:bg-brand-900 text-brand-700 dark:text-brand-300 border-brand-200 dark:border-brand-800'
                    : 'bg-white dark:bg-surface-900 text-surface-400 dark:text-surface-500 border-surface-200 dark:border-surface-800'
              ]"
            >
              <span v-if="currentStep > step.id" class="text-xs">&#10003;</span>
              <span v-else>{{ step.id }}</span>
            </div>
            <span
              class="hidden truncate text-[11px] font-medium md:inline"
              :class="currentStep >= step.id ? 'text-surface-900 dark:text-surface-100' : 'text-surface-400 dark:text-surface-500'"
            >
              {{ step.title }}
            </span>
          </div>
          <div
            v-if="idx < steps.length - 1"
            class="mx-1.5 h-px flex-1 rounded-full transition-colors"
            :class="currentStep > step.id ? 'bg-brand-600' : 'bg-surface-200 dark:bg-surface-800'"
          />
        </li>
      </ol>

      <div v-if="!isPublished" class="flex shrink-0 items-center gap-1">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-surface-800 dark:hover:text-surface-100"
          @click="openDraftPreview"
        >
          <Eye class="size-3.5" />
          <span class="hidden sm:inline">View preview</span>
        </button>
        <button
          type="button"
          class="rounded-md px-2 py-1 text-xs font-medium text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-900 disabled:opacity-50 dark:text-surface-400 dark:hover:bg-surface-800 dark:hover:text-surface-100"
          :disabled="isSubmitting"
          @click="handleSubmit('draft')"
        >
          Save &amp; exit
        </button>
      </div>
    </div>

    <!-- Main Layout: editor + persistent live preview -->
    <div
      class="grid gap-6 xl:min-h-0 xl:flex-1"
      :class="currentStep <= 2
        ? 'xl:grid-cols-[minmax(0,3fr)_minmax(24rem,2fr)]'
        : 'mx-auto w-full max-w-3xl xl:grid-cols-1'"
    >
      <div
        ref="wizardEditor"
        class="min-w-0 space-y-6 xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain xl:pb-1 xl:pr-1"
      >

        <div class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 shadow-sm overflow-hidden">
          <form @submit.prevent="() => handleSubmit()" class="p-5 md:p-6">
            <!-- Step 1: Job details -->
            <section v-if="currentStep === 1" class="space-y-6">
              <div>
                <h2 class="text-lg font-semibold text-surface-900 dark:text-surface-100">Job details</h2>
                <p class="text-sm text-surface-500 dark:text-surface-400 mt-1">Only the job title is required — everything else can be added later.</p>
              </div>

              <!-- Title -->
              <div>
                <label for="title" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                  Job title <span class="text-danger-500">*</span>
                </label>
                <input
                  id="title"
                  v-model="form.title"
                  type="text"
                  maxlength="200"
                  placeholder="e.g. Senior Frontend Engineer"
                  class="w-full rounded-lg border px-3 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors"
                  :class="errors.title ? 'border-danger-300 ring-1 ring-danger-100' : 'border-surface-300 dark:border-surface-700'"
                  @blur="validateStep1"
                />
                <p v-if="errors.title" class="mt-1.5 text-xs text-danger-600 dark:text-danger-400 font-medium">{{ errors.title }}</p>
              </div>

              <!-- Location + employment type -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label for="location" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                    Location
                  </label>
                  <input
                    id="location"
                    v-model="form.location"
                    type="text"
                    maxlength="500"
                    placeholder="e.g. New York, NY"
                    class="w-full rounded-lg border px-3 py-2.5 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors border-surface-300 dark:border-surface-700"
                  />
                </div>
                <div>
                  <label for="type" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                    Employment type
                  </label>
                  <select
                    id="type"
                    v-model="form.type"
                    class="w-full rounded-lg border px-3 py-2.5 text-sm text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors bg-white dark:bg-surface-900 border-surface-300 dark:border-surface-700"
                  >
                    <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                </div>
              </div>

              <!-- Experience + remote -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label for="experienceLevel" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">Experience level</label>
                  <select
                    id="experienceLevel"
                    v-model="form.experienceLevel"
                    class="w-full rounded-lg border px-3 py-2.5 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 border-surface-300 dark:border-surface-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors"
                  >
                    <option value="junior">Junior</option>
                    <option value="mid">Mid-level</option>
                    <option value="senior">Senior</option>
                    <option value="lead">Lead</option>
                  </select>
                </div>
                <div>
                  <label for="remoteStatus" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">Workplace</label>
                  <select
                    id="remoteStatus"
                    v-model="form.remoteStatus"
                    class="w-full rounded-lg border px-3 py-2.5 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 border-surface-300 dark:border-surface-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors"
                  >
                    <option :value="undefined">Not specified</option>
                    <option value="remote">Remote</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">On-site</option>
                  </select>
                </div>
              </div>

              <!-- Description -->
              <div>
                <label for="description" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
                  Description
                </label>
                <textarea
                  id="description"
                  v-model="form.description"
                  rows="8"
                  placeholder="Describe the role, responsibilities, and requirements…"
                  class="w-full rounded-lg border px-4 py-3 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors border-surface-300 dark:border-surface-700"
                />
                <p class="mt-1.5 text-xs text-surface-500">A clear description improves AI scoring and attracts better candidates.</p>
              </div>
            </section>

            <!-- Step 2: Application form -->
            <!-- Step 2: Application form (live builder) -->
            <section v-else-if="currentStep === 2">
              <ApplicationBuilder
                v-model="applicationForm"
                :job-title="form.title"
                :show-preview="false"
              />
            </section>

            <!-- Step 3: AI scoring criteria -->
            <section v-else-if="currentStep === 3" class="space-y-8">

              <div>
                <div class="flex items-center gap-2">
                  <h2 class="text-lg font-semibold text-surface-900 dark:text-surface-100">Candidate scoring</h2>
                  <span class="inline-flex items-center rounded-md bg-surface-100 dark:bg-surface-800 px-2 py-0.5 text-[10px] font-medium text-surface-500 dark:text-surface-400">Optional</span>
                </div>
                <p class="text-sm text-surface-500 dark:text-surface-400 mt-1">
                  <span class="font-medium text-surface-700 dark:text-surface-300">This step is optional — you can skip it and set up scoring later from job settings.</span>
                  If you'd like AI to score and rank every applicant, we've recommended a set of criteria for this role below; use it as-is or customize.
                </p>
              </div>

                <!-- Recommended default: one-click, zero decisions -->
                <div v-if="scoringCriteria.length === 0 && !showAdvanced" class="space-y-5">
                  <div class="relative overflow-hidden rounded-2xl border border-brand-200/80 dark:border-brand-800/60 bg-gradient-to-br from-brand-50 via-white to-white dark:from-brand-950/40 dark:via-surface-900 dark:to-surface-900 p-6 shadow-sm">
                    <!-- Decorative glow -->
                    <div class="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-brand-200/30 dark:bg-brand-700/10 blur-3xl" />

                    <div class="relative flex items-start gap-4">
                      <div class="inline-flex items-center justify-center size-11 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-sm shadow-brand-600/20 shrink-0">
                        <Sparkles class="size-5" />
                      </div>
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                          <h3 class="text-base font-semibold text-surface-900 dark:text-surface-100">Recommended scoring</h3>
                          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset bg-brand-100 text-brand-700 ring-brand-200 dark:bg-brand-950/60 dark:text-brand-300 dark:ring-brand-800">
                            {{ recommendedCriteria.length }} criteria
                          </span>
                        </div>
                        <p class="text-sm text-surface-500 dark:text-surface-400 mt-1 leading-relaxed">
                          A balanced set tailored to this role. AI ranks every applicant against these — you can tweak or remove any of them after.
                        </p>

                        <!-- Criteria preview chips -->
                        <ul class="flex flex-wrap gap-2 mt-4">
                          <li
                            v-for="c in recommendedCriteria"
                            :key="c.key"
                            class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium ring-1 ring-inset"
                            :class="categoryColorClasses[c.category] ?? categoryColorClasses.custom"
                          >
                            {{ c.name }}
                          </li>
                        </ul>

                        <div class="flex flex-wrap items-center gap-2.5 mt-5">
                          <button
                            type="button"
                            class="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brand-600/20 hover:bg-brand-700 active:scale-[0.99] transition-all"
                            @click="useRecommendedScoring"
                          >
                            <Check class="size-4" />
                            Use recommended scoring
                          </button>
                          <button
                            type="button"
                            class="inline-flex items-center gap-1.5 rounded-lg border border-surface-200 dark:border-surface-700 px-4 py-2.5 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                            @click="showAdvanced = true"
                          >
                            <SlidersHorizontal class="size-4" />
                            Customize instead
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Skip option -->
                  <div class="flex items-center gap-3">
                    <div class="h-px flex-1 bg-surface-200 dark:bg-surface-800" />
                    <span class="text-xs font-medium text-surface-400 dark:text-surface-500">or</span>
                    <div class="h-px flex-1 bg-surface-200 dark:bg-surface-800" />
                  </div>
                  <button
                    type="button"
                    class="group flex w-full items-center gap-3 rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 px-5 py-4 text-left hover:border-surface-300 dark:hover:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/50 transition-colors"
                    @click="skipScoring"
                  >
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-surface-100 dark:bg-surface-800 text-surface-500 dark:text-surface-400 shrink-0">
                      <ArrowRight class="size-5" />
                    </div>
                    <div class="flex-1 min-w-0">
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Skip scoring for now</span>
                      <span class="block text-xs text-surface-500 dark:text-surface-400 mt-0.5">Continue without AI scoring — you can set this up anytime from job settings.</span>
                    </div>
                    <ChevronRight class="size-5 text-surface-300 dark:text-surface-600 group-hover:text-surface-400 dark:group-hover:text-surface-500 transition-colors shrink-0" />
                  </button>
                </div>

                <!-- Back to recommended (from advanced) -->
                <button
                  v-if="scoringCriteria.length === 0 && showAdvanced"
                  type="button"
                  class="inline-flex items-center gap-1.5 text-xs font-medium text-surface-500 hover:text-surface-800 dark:text-surface-400 dark:hover:text-surface-200 transition-colors"
                  @click="showAdvanced = false"
                >
                  <ArrowLeft class="size-3.5" />
                  Back to recommended
                </button>

                <!-- AI not configured warning -->
                <div v-if="!isAiConfigured && showAdvanced" class="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-5">
                  <div class="flex items-start gap-3">
                    <Sparkles class="size-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p class="text-sm font-semibold text-amber-800 dark:text-amber-200">AI provider not configured</p>
                      <p class="text-xs text-amber-700 dark:text-amber-300 mt-1 leading-relaxed">
                        To use AI-powered scoring, you need to configure an AI provider first. You can still define criteria manually and set up AI later.
                      </p>
                      <NuxtLink
                        :to="$localePath('/dashboard/settings/ai')"
                        class="inline-flex items-center gap-1.5 mt-3 text-xs font-medium text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 underline underline-offset-2"
                      >
                        <ExternalLink class="size-3" />
                        Go to AI settings
                      </NuxtLink>
                    </div>
                  </div>
                </div>

                <!-- Mode selection cards -->
                <div v-if="scoringCriteria.length === 0 && showAdvanced" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <!-- Pre-made templates -->
                  <button
                    type="button"
                    class="relative flex flex-col items-start gap-3 p-5 rounded-xl border-2 text-left transition-all hover:shadow-md"
                    :class="scoringMode === 'premade'
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50/70 dark:bg-brand-950/30 ring-2 ring-brand-200 dark:ring-brand-900'
                      : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'"
                    @click="scoringMode = 'premade'"
                  >
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-brand-100 dark:bg-brand-900/50">
                      <Brain class="size-5 text-brand-600 dark:text-brand-400" />
                    </div>
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Pre-made templates</span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-1 block leading-relaxed">
                        Choose from expert-designed scoring rubrics for common role types.
                      </span>
                    </div>
                  </button>

                  <!-- AI from job description -->
                  <button
                    type="button"
                    :disabled="!isAiConfigured"
                    class="relative flex flex-col items-start gap-3 p-5 rounded-xl border-2 text-left transition-all hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    :class="scoringMode === 'ai'
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50/70 dark:bg-brand-950/30 ring-2 ring-brand-200 dark:ring-brand-900'
                      : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'"
                    @click="generateAiCriteria()"
                  >
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-purple-100 dark:bg-purple-900/50">
                      <Sparkles class="size-5 text-purple-600 dark:text-purple-400" />
                    </div>
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Generate from job description</span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-1 block leading-relaxed">
                        AI analyzes your job description and creates tailored criteria.
                      </span>
                      <span v-if="!isAiConfigured" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1 block">
                        Requires AI provider setup
                      </span>
                    </div>
                    <span v-if="isGeneratingCriteria" class="absolute top-3 right-3">
                      <Loader2 class="size-4 text-purple-600 animate-spin" />
                    </span>
                  </button>

                  <!-- Custom criteria -->
                  <button
                    type="button"
                    class="relative flex flex-col items-start gap-3 p-5 rounded-xl border-2 text-left transition-all hover:shadow-md"
                    :class="scoringMode === 'custom'
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50/70 dark:bg-brand-950/30 ring-2 ring-brand-200 dark:ring-brand-900'
                      : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'"
                    @click="scoringMode = 'custom'; showCustomForm = true"
                  >
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-emerald-100 dark:bg-emerald-900/50">
                      <SlidersHorizontal class="size-5 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Write your own</span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-1 block leading-relaxed">
                        Create custom scoring criteria tailored to your exact needs.
                      </span>
                    </div>
                  </button>
                </div>

                <!-- Pre-made template selector -->
                <div v-if="scoringMode === 'premade' && scoringCriteria.length === 0 && showAdvanced" class="space-y-4 mt-4">
                  <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <button
                      v-for="tmpl in [
                        { key: 'standard', label: 'Standard', desc: '3 balanced criteria for any role' },
                        { key: 'technical', label: 'Technical', desc: '5 criteria focused on engineering' },
                        { key: 'non_technical', label: 'Non-Technical', desc: '5 criteria for business roles' },
                      ] as const"
                      :key="tmpl.key"
                      type="button"
                      class="p-4 rounded-lg border text-left transition-all"
                      :class="selectedTemplate === tmpl.key
                        ? 'border-brand-400 dark:border-brand-600 bg-brand-50 dark:bg-brand-950/30'
                        : 'border-surface-200 dark:border-surface-800 hover:bg-surface-50 dark:hover:bg-surface-800/50'"
                      @click="selectedTemplate = tmpl.key; loadPremadeCriteria(tmpl.key)"
                    >
                      <span class="block text-sm font-medium text-surface-900 dark:text-surface-100">{{ tmpl.label }}</span>
                      <span class="text-xs text-surface-500">{{ tmpl.desc }}</span>
                    </button>
                  </div>
                </div>

                <!-- Criteria list with weight sliders -->
                <div v-if="scoringCriteria.length > 0" class="space-y-4">
                  <div class="flex items-center justify-between">
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 text-xs font-medium text-surface-500 hover:text-surface-800 dark:text-surface-400 dark:hover:text-surface-200 transition-colors"
                      @click="scoringCriteria = []; scoringMode = 'none'; showAdvanced = false"
                    >
                      <ArrowLeft class="size-3.5" />
                      Back to options
                    </button>
                    <h3 class="text-sm font-semibold text-surface-800 dark:text-surface-200">
                      {{ scoringCriteria.length }} {{ scoringCriteria.length === 1 ? 'criterion' : 'criteria' }} configured
                    </h3>
                  </div>

                  <div class="space-y-3">
                    <div
                      v-for="criterion in scoringCriteria"
                      :key="criterion.key"
                      class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-950 p-4 transition-all hover:shadow-sm"
                    >
                      <div class="flex items-start justify-between gap-3 mb-3">
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center gap-2 mb-1">
                            <span class="text-sm font-semibold text-surface-900 dark:text-surface-100">{{ criterion.name }}</span>
                            <span
                              class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset"
                              :class="categoryColorClasses[criterion.category] ?? categoryColorClasses.custom"
                            >
                              {{ categoryLabels[criterion.category] ?? criterion.category }}
                            </span>
                          </div>
                          <p v-if="criterion.description" class="text-xs text-surface-500 dark:text-surface-400 leading-relaxed">
                            {{ criterion.description }}
                          </p>
                        </div>
                        <button
                          type="button"
                          class="rounded p-1 text-surface-400 hover:text-danger-600 dark:hover:text-danger-400 hover:bg-danger-50 dark:hover:bg-danger-950 transition-colors shrink-0"
                          title="Remove"
                          @click="removeCriterion(criterion.key)"
                        >
                          <Trash2 class="size-4" />
                        </button>
                      </div>

                      <!-- Weight slider -->
                      <div class="flex items-center gap-4">
                        <label class="text-xs font-medium text-surface-500 dark:text-surface-400 shrink-0 w-12">Weight</label>
                        <input
                          type="range"
                          :min="0"
                          :max="100"
                          v-model.number="criterion.weight"
                          class="flex-1 h-2 rounded-lg appearance-none cursor-pointer accent-brand-600 bg-surface-200 dark:bg-surface-700"
                        />
                        <span class="text-xs font-mono font-semibold text-surface-700 dark:text-surface-300 w-8 text-right">
                          {{ criterion.weight }}
                        </span>
                      </div>

                      <div class="flex items-center gap-4 mt-2 text-xs text-surface-400">
                        <span>Max score: {{ criterion.maxScore }}</span>
                        <span>Key: <code class="rounded bg-surface-100 dark:bg-surface-800 px-1 py-0.5 font-mono text-[10px]">{{ criterion.key }}</code></span>
                      </div>
                    </div>
                  </div>

                  <!-- Add another criterion -->
                  <button
                    v-if="!showCustomForm"
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-surface-300 dark:border-surface-700 px-3 py-2 text-sm font-medium text-surface-600 dark:text-surface-400 hover:border-brand-400 dark:hover:border-brand-600 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950 transition-colors"
                    @click="showCustomForm = true"
                  >
                    <Plus class="size-4" />
                    Add criterion
                  </button>
                </div>

                <!-- Custom criterion form -->
                <div v-if="showCustomForm" class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50 p-5 space-y-4">
                  <h3 class="text-sm font-semibold text-surface-800 dark:text-surface-200">Add custom criterion</h3>
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label class="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">Name *</label>
                      <input
                        v-model="customCriterionForm.name"
                        @input="customCriterionForm.key = autoGenerateKey(customCriterionForm.name)"
                        type="text"
                        maxlength="200"
                        placeholder="e.g. React Expertise"
                        class="w-full rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-2 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                      />
                    </div>
                    <div>
                      <label class="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">Category</label>
                      <select
                        v-model="customCriterionForm.category"
                        class="w-full rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-2 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                      >
                        <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label class="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">Description</label>
                    <textarea
                      v-model="customCriterionForm.description"
                      rows="2"
                      maxlength="1000"
                      placeholder="Describe what the AI should evaluate for this criterion..."
                      class="w-full rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-2 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                  <div class="grid grid-cols-2 gap-4">
                    <div>
                      <label class="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">Max Score</label>
                      <input
                        v-model.number="customCriterionForm.maxScore"
                        type="number"
                        min="1"
                        max="100"
                        class="w-full rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-2 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                      />
                    </div>
                    <div>
                      <label class="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">Initial Weight (0–100)</label>
                      <input
                        v-model.number="customCriterionForm.weight"
                        type="number"
                        min="0"
                        max="100"
                        class="w-full rounded-lg border border-surface-300 dark:border-surface-700 px-3 py-2 text-sm bg-white dark:bg-surface-900 text-surface-900 dark:text-surface-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                      />
                    </div>
                  </div>
                  <div class="flex items-center gap-3 pt-2">
                    <button
                      type="button"
                      :disabled="!customCriterionForm.name"
                      class="px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      @click="addCustomCriterion"
                    >
                      Add criterion
                    </button>
                    <button
                      type="button"
                      class="px-4 py-2 text-sm font-medium text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 rounded-lg transition-colors"
                      @click="showCustomForm = false"
                    >
                      Cancel
                    </button>
                  </div>
                </div>

                <!-- Auto-score toggle -->
                <div v-if="scoringCriteria.length > 0" class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50 p-5">
                  <label class="flex items-start gap-3 cursor-pointer">
                    <input
                      v-model="autoScoreOnApply"
                      type="checkbox"
                      :disabled="!isAiConfigured"
                      class="mt-0.5 size-4 rounded border-surface-300 dark:border-surface-600 text-brand-600 focus:ring-brand-500 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">
                        Automatically score every new applicant
                      </span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-0.5 block leading-relaxed">
                        When a candidate applies, AI will automatically analyze their resume against these criteria and assign a score. Requires an AI provider configured in settings plus a resume upload.
                      </span>
                      <span v-if="!isAiConfigured" class="text-xs text-amber-600 dark:text-amber-400 mt-1 block">
                        <NuxtLink :to="$localePath('/dashboard/settings/ai')" class="underline underline-offset-2 hover:text-amber-800 dark:hover:text-amber-200">Configure an AI provider</NuxtLink> to enable automatic scoring.
                      </span>
                    </div>
                  </label>
                </div>

            </section>

            <!-- Step 4: Publish & Distribute -->
            <section v-else-if="currentStep === 4" class="space-y-8">
              <!-- Success state after publishing -->
              <div v-if="isPublished" class="space-y-8">
                <!-- Compact success header -->
                <div class="flex items-center gap-4 rounded-xl border border-success-200 dark:border-success-800 bg-success-50 dark:bg-success-950/30 p-5">
                  <div class="inline-flex items-center justify-center size-12 rounded-full bg-success-100 dark:bg-success-900/50 shrink-0">
                    <PartyPopper class="size-6 text-success-600 dark:text-success-400" />
                  </div>
                  <div class="flex-1 min-w-0">
                    <h2 class="text-lg font-bold text-surface-900 dark:text-surface-100">Your job is live!</h2>
                    <p class="text-sm text-surface-500 dark:text-surface-400">
                      <strong>{{ form.title }}</strong> is now accepting applications.
                    </p>
                  </div>
                  <NuxtLink
                    :to="finalApplicationLink"
                    target="_blank"
                    class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium text-brand-700 dark:text-brand-300 bg-brand-100 dark:bg-brand-900/50 rounded-lg hover:bg-brand-200 dark:hover:bg-brand-800 transition-colors shrink-0"
                  >
                    <ExternalLink class="size-3.5" />
                    Preview
                  </NuxtLink>
                </div>

                <!-- Direct application link -->
                <div class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50 p-5">
                  <div class="flex items-center gap-2 mb-3">
                    <Link2 class="size-4 text-surface-500 dark:text-surface-400" />
                    <span class="text-sm font-semibold text-surface-700 dark:text-surface-300">Direct application link</span>
                    <span class="text-xs text-surface-400 dark:text-surface-500">(no tracking)</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <input
                      type="text"
                      readonly
                      :value="finalApplicationLink"
                      class="flex-1 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 px-3 py-2 text-sm text-surface-600 dark:text-surface-400 select-all font-mono"
                    />
                    <button
                      type="button"
                      class="inline-flex items-center gap-1.5 rounded-lg bg-surface-200 dark:bg-surface-700 px-4 py-2 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-300 dark:hover:bg-surface-600 transition-colors shrink-0"
                      @click="copyFinalLink"
                    >
                      <Copy class="size-3.5" />
                      {{ linkCopiedFinal ? 'Copied!' : 'Copy' }}
                    </button>
                  </div>
                </div>

                <!-- Distribution hub -->
                <div>
                  <div class="flex items-center gap-3 mb-2">
                    <Share2 class="size-5 text-brand-600 dark:text-brand-400" />
                    <h3 class="text-lg font-semibold text-surface-900 dark:text-surface-100">Share &amp; track</h3>
                  </div>
                  <p class="text-sm text-surface-500 dark:text-surface-400 mb-6">
                    Create tracked links for each platform. This lets you see exactly where your applicants come from.
                  </p>

                  <!-- Channel groups -->
                  <div
                    v-for="group in distributionGroups"
                    :key="group.key"
                    class="mb-6"
                  >
                    <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-3">{{ group.label }}</h4>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div
                        v-for="ch in distributionChannels.filter(c => c.category === group.key)"
                        :key="ch.channel"
                        class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-950 p-4 transition-all"
                        :class="createdLinks[ch.channel]?.code ? 'ring-1 ring-brand-200 dark:ring-brand-800 border-brand-200 dark:border-brand-800' : ''"
                      >
                        <div class="flex items-start gap-3">
                          <div class="inline-flex items-center justify-center size-9 rounded-lg bg-surface-100 dark:bg-surface-800 shrink-0">
                            <component :is="channelIcons[ch.channel] ?? Globe" class="size-4 text-surface-500 dark:text-surface-400" />
                          </div>
                          <div class="flex-1 min-w-0">
                            <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">{{ ch.name }}</span>
                            <span class="text-xs text-surface-400 dark:text-surface-500">{{ ch.description }}</span>
                          </div>
                        </div>

                        <!-- Not yet created -->
                        <div v-if="!createdLinks[ch.channel]" class="mt-3">
                          <button
                            type="button"
                            class="w-full inline-flex items-center justify-center gap-1.5 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/30 px-3 py-2 text-xs font-medium text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-colors"
                            @click="createChannelLink(ch.channel, ch.name)"
                          >
                            <Plus class="size-3.5" />
                            Create tracking link
                          </button>
                        </div>

                        <!-- Loading -->
                        <div v-else-if="createdLinks[ch.channel]?.loading" class="mt-3 flex items-center justify-center gap-2 py-2">
                          <Loader2 class="size-3.5 text-brand-600 animate-spin" />
                          <span class="text-xs text-surface-500">Creating...</span>
                        </div>

                        <!-- Created - show URL -->
                        <div v-else class="mt-3 space-y-2">
                          <div class="flex items-center gap-1.5">
                            <input
                              type="text"
                              readonly
                              :value="createdLinks[ch.channel]?.url"
                              class="flex-1 rounded-md border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900 px-2.5 py-1.5 text-xs text-surface-600 dark:text-surface-400 select-all font-mono truncate"
                            />
                            <button
                              type="button"
                              class="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors shrink-0"
                              :class="createdLinks[ch.channel]?.copied
                                ? 'bg-success-100 dark:bg-success-900/50 text-success-700 dark:text-success-300'
                                : 'bg-brand-600 text-white hover:bg-brand-700'"
                              @click="copyChannelLink(ch.channel)"
                            >
                              <Check v-if="createdLinks[ch.channel]?.copied" class="size-3" />
                              <Copy v-else class="size-3" />
                              {{ createdLinks[ch.channel]?.copied ? 'Copied!' : 'Copy' }}
                            </button>
                          </div>
                          <p class="flex items-center gap-1 text-[11px] text-success-600 dark:text-success-400">
                            <Check class="size-3" />
                            Clicks and applications from this link will be tracked
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Custom job board -->
                  <div class="mb-6">
                    <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-3">Custom job board</h4>
                    <p class="text-sm text-surface-500 dark:text-surface-400 mb-3">
                      Create a tracked link for any platform not listed above.
                    </p>

                    <!-- Add custom board form -->
                    <div class="flex items-center gap-2 mb-4">
                      <input
                        v-model="customBoardName"
                        type="text"
                        placeholder="e.g. Hacker News, AngelList, Niche Board"
                        class="flex-1 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 px-3 py-2 text-sm text-surface-700 dark:text-surface-300 placeholder-surface-400 dark:placeholder-surface-500 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                        @keydown.enter.prevent="createCustomBoardLink"
                      />
                      <button
                        type="button"
                        class="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/30 px-4 py-2 text-sm font-medium text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-colors shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                        :disabled="!customBoardName.trim() || isCreatingCustomBoard"
                        @click="createCustomBoardLink"
                      >
                        <Loader2 v-if="isCreatingCustomBoard" class="size-3.5 animate-spin" />
                        <Plus v-else class="size-3.5" />
                        Create link
                      </button>
                    </div>

                    <!-- Created custom board links -->
                    <div v-if="customBoardLinks.length" class="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div
                        v-for="(cbl, idx) in customBoardLinks"
                        :key="cbl.channel"
                        class="rounded-xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-950 p-4 ring-1 ring-brand-200 dark:ring-brand-800 border-brand-200 dark:border-brand-800"
                      >
                        <div class="flex items-start gap-3">
                          <div class="inline-flex items-center justify-center size-9 rounded-lg bg-surface-100 dark:bg-surface-800 shrink-0">
                            <Globe class="size-4 text-surface-500 dark:text-surface-400" />
                          </div>
                          <div class="flex-1 min-w-0">
                            <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">{{ cbl.name }}</span>
                            <span class="text-xs text-surface-400 dark:text-surface-500">Custom job board</span>
                          </div>
                        </div>
                        <div class="mt-3 space-y-2">
                          <div class="flex items-center gap-1.5">
                            <input
                              type="text"
                              readonly
                              :value="cbl.url"
                              class="flex-1 rounded-md border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900 px-2.5 py-1.5 text-xs text-surface-600 dark:text-surface-400 select-all font-mono truncate"
                            />
                            <button
                              type="button"
                              class="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors shrink-0"
                              :class="cbl.copied
                                ? 'bg-success-100 dark:bg-success-900/50 text-success-700 dark:text-success-300'
                                : 'bg-brand-600 text-white hover:bg-brand-700'"
                              @click="copyCustomBoardLink(idx)"
                            >
                              <Check v-if="cbl.copied" class="size-3" />
                              <Copy v-else class="size-3" />
                              {{ cbl.copied ? 'Copied!' : 'Copy' }}
                            </button>
                          </div>
                          <p class="flex items-center gap-1 text-[11px] text-success-600 dark:text-success-400">
                            <Check class="size-3" />
                            Clicks and applications from this link will be tracked
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Summary and link to full dashboard -->
                  <div class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50 p-4">
                    <div class="flex items-center gap-3">
                      <BarChart3 class="size-5 text-surface-400 dark:text-surface-500 shrink-0" />
                      <div class="flex-1">
                        <p class="text-sm text-surface-700 dark:text-surface-300">
                          <span v-if="createdLinkCount > 0">
                            {{ createdLinkCount }} tracking {{ createdLinkCount === 1 ? 'link' : 'links' }} created.
                          </span>
                          View all analytics and manage links in the
                          <NuxtLink :to="$localePath('/dashboard/source-tracking')" class="text-brand-600 dark:text-brand-400 font-medium underline underline-offset-2">Source Tracking dashboard</NuxtLink>.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Action buttons -->
                <div class="flex items-center justify-between pt-6 border-t border-surface-100 dark:border-surface-800">
                  <NuxtLink
                    :to="$localePath(`/dashboard/jobs/${createdJobId}`)"
                    class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-surface-700 dark:text-surface-300 bg-white dark:bg-surface-900 border border-surface-300 dark:border-surface-700 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                  >
                    <Eye class="size-4" />
                    View job
                  </NuxtLink>
                  <NuxtLink
                    :to="$localePath('/dashboard')"
                    class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors shadow-sm"
                  >
                    Go to dashboard
                  </NuxtLink>
                </div>
              </div>

              <!-- Pre-publish state: choose publish or draft -->
              <div v-else>
                <h2 class="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-2 pb-2 border-b border-surface-100 dark:border-surface-800">Ready to go?</h2>
                <p class="text-sm text-surface-500 dark:text-surface-400 mb-6">
                  Publish your job to start receiving applications. After publishing, you'll be able to create tracked links for each platform where you share it.
                </p>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                  <!-- Publish now option -->
                  <button
                    type="button"
                    class="relative flex flex-col items-start gap-3 p-5 rounded-xl border-2 text-left transition-all"
                    :class="publishChoice === 'publish'
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50/70 dark:bg-brand-950/30 ring-2 ring-brand-200 dark:ring-brand-900'
                      : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/50'"
                    @click="publishChoice = 'publish'"
                  >
                    <span
                      v-if="publishChoice === 'publish'"
                      class="absolute top-3 right-3 inline-flex items-center justify-center size-5 rounded-full bg-brand-600 text-white"
                    >
                      <Check class="size-3" />
                    </span>
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-brand-100 dark:bg-brand-900/50">
                      <Rocket class="size-5 text-brand-600 dark:text-brand-400" />
                    </div>
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Publish now</span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-1 block leading-relaxed">
                        Your job goes live immediately. The application link will be copied to your clipboard so you can share it right away.
                      </span>
                    </div>
                  </button>

                  <!-- Save as draft option -->
                  <button
                    type="button"
                    class="relative flex flex-col items-start gap-3 p-5 rounded-xl border-2 text-left transition-all"
                    :class="publishChoice === 'draft'
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50/70 dark:bg-brand-950/30 ring-2 ring-brand-200 dark:ring-brand-900'
                      : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/50'"
                    @click="publishChoice = 'draft'"
                  >
                    <span
                      v-if="publishChoice === 'draft'"
                      class="absolute top-3 right-3 inline-flex items-center justify-center size-5 rounded-full bg-brand-600 text-white"
                    >
                      <Check class="size-3" />
                    </span>
                    <div class="inline-flex items-center justify-center size-10 rounded-lg bg-surface-100 dark:bg-surface-800">
                      <FileEdit class="size-5 text-surface-500 dark:text-surface-400" />
                    </div>
                    <div>
                      <span class="block text-sm font-semibold text-surface-900 dark:text-surface-100">Save as draft</span>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-1 block leading-relaxed">
                        Save for later review. The job won't be visible to candidates until you publish it.
                      </span>
                    </div>
                  </button>
                </div>

                <!-- Summary of what was configured -->
                <div class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50 p-5">
                  <h3 class="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-4">Job summary</h3>
                  <dl class="space-y-3 text-sm">
                    <div class="flex items-start gap-3">
                      <dt class="flex items-center gap-1.5 text-surface-500 dark:text-surface-400 shrink-0 w-32">
                        <Briefcase class="size-3.5" /> Title
                      </dt>
                      <dd class="text-surface-900 dark:text-surface-100 font-medium">{{ form.title }}</dd>
                    </div>
                    <div v-if="form.location" class="flex items-start gap-3">
                      <dt class="flex items-center gap-1.5 text-surface-500 dark:text-surface-400 shrink-0 w-32">
                        <Link2 class="size-3.5" /> Location
                      </dt>
                      <dd class="text-surface-900 dark:text-surface-100">{{ form.location }}</dd>
                    </div>
                    <div class="flex items-start gap-3">
                      <dt class="flex items-center gap-1.5 text-surface-500 dark:text-surface-400 shrink-0 w-32">
                        <FileText class="size-3.5" /> Resume
                      </dt>
                      <dd class="text-surface-900 dark:text-surface-100">{{ applicationForm.requireResume ? 'Required' : 'Optional' }}</dd>
                    </div>
                    <div class="flex items-start gap-3">
                      <dt class="flex items-center gap-1.5 text-surface-500 dark:text-surface-400 shrink-0 w-32">
                        <MessageSquare class="size-3.5" /> Questions
                      </dt>
                      <dd class="text-surface-900 dark:text-surface-100">{{ applicationForm.questions.length }} custom {{ applicationForm.questions.length === 1 ? 'question' : 'questions' }}</dd>
                    </div>
                  </dl>
                </div>

                <!-- What happens next hint -->
                <div v-if="publishChoice === 'publish'" class="rounded-xl border border-brand-100 dark:border-brand-900 bg-brand-50/50 dark:bg-brand-950/20 p-4 mt-6">
                  <div class="flex items-start gap-3">
                    <Share2 class="size-4 text-brand-600 dark:text-brand-400 shrink-0 mt-0.5" />
                    <div>
                      <p class="text-sm font-medium text-brand-800 dark:text-brand-200">After publishing</p>
                      <p class="text-xs text-brand-700 dark:text-brand-300 mt-0.5 leading-relaxed">
                        You'll get tracked links for LinkedIn, Indeed, and other platforms so you can see exactly where your applicants come from.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <!-- Actions Footer -->
            <div v-if="!isPublished" class="flex items-center justify-between mt-12 pt-8 border-t border-surface-100 dark:border-surface-800">
              <NuxtLink
                :to="$localePath('/dashboard')"
                class="px-6 py-2.5 text-sm font-medium text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
              >
                Cancel
              </NuxtLink>

              <div class="flex items-center gap-3">
                <button
                  v-if="currentStep > 1"
                  type="button"
                  @click="prevStep"
                  class="px-6 py-2.5 text-sm font-medium text-surface-700 dark:text-surface-300 bg-white dark:bg-surface-900 border border-surface-300 dark:border-surface-700 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                >
                  Back
                </button>
                <button
                  v-if="currentStep < 4"
                  type="button"
                  :disabled="!canGoNext"
                  @click="nextStep"
                  class="px-8 py-2.5 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                >
                  Save &amp; continue
                </button>
                <button
                  v-else
                  type="submit"
                  :disabled="isSubmitting"
                  class="inline-flex items-center gap-2 px-8 py-2.5 text-sm font-medium text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                  :class="publishChoice === 'publish' ? 'bg-brand-600 hover:bg-brand-700' : 'bg-surface-600 hover:bg-surface-700'"
                >
                  <Rocket v-if="publishChoice === 'publish'" class="size-4" />
                  <FileEdit v-else class="size-4" />
                  {{ isSubmitting
                    ? (publishChoice === 'publish' ? 'Publishing...' : 'Saving...')
                    : (publishChoice === 'publish' ? 'Publish & copy link' : 'Save as draft')
                  }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      <aside
        v-if="currentStep <= 2"
        class="hidden min-w-0 xl:block xl:min-h-0 xl:overflow-hidden"
      >
        <ApplicationBuilderPreview
          :application-form="applicationForm"
          :job-details="form"
          max-height="100%"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
button:not(:disabled) {
  cursor: pointer;
}
</style>
