<script setup lang="ts">
import { Upload, X } from 'lucide-vue-next'

/**
 * Renders a custom question as the appropriate form field based on its type.
 * Used on the public application form to display recruiter-configured questions.
 *
 * For `file_upload` type questions, emits `file-selected` with the File object.
 * The model value will be set to `"pending:<filename>"` to track selection state.
 */
const props = defineProps<{
  question: {
    id: string
    type: string
    label: string
    description?: string | null
    required: boolean
    options?: string[] | null
  }
  error?: string
}>()

const emit = defineEmits<{
  (e: 'file-selected', questionId: string, file: File | null): void
}>()

const model = defineModel<string | string[] | number | boolean | undefined>()

// String-coerced model for text inputs (avoids TS error with boolean in v-model on <input>)
const stringModel = computed({
  get: () => (model.value as string) ?? '',
  set: (v: string) => { model.value = v },
})

const numberModel = computed({
  get: () => (model.value as number) ?? undefined,
  set: (v: number) => { model.value = v },
})

const booleanModel = computed({
  get: () => (model.value as boolean) ?? false,
  set: (v: boolean) => { model.value = v },
})

// For multi_select, ensure model value is always an array
if (props.question.type === 'multi_select' && !Array.isArray(model.value)) {
  model.value = []
}

// For checkbox, ensure model value is always a boolean
if (props.question.type === 'checkbox' && typeof model.value !== 'boolean') {
  model.value = false
}

function toggleMultiOption(option: string) {
  const current = Array.isArray(model.value) ? [...model.value] : []
  const idx = current.indexOf(option)
  if (idx >= 0) {
    current.splice(idx, 1)
  } else {
    current.push(option)
  }
  model.value = current
}

function isOptionSelected(option: string): boolean {
  return Array.isArray(model.value) && model.value.includes(option)
}

// ─────────────────────────────────────────────
// File upload handling
// ─────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFileName = ref<string | null>(null)

/** Accepted file types for file_upload questions */
const acceptedFileTypes = '.pdf,.doc,.docx'

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null

  if (file) {
    selectedFileName.value = file.name
    // Store a marker in the model so required-field validation knows a file is selected
    model.value = `pending:${file.name}`
    emit('file-selected', props.question.id, file)
  } else {
    clearFile()
  }
}

function clearFile() {
  selectedFileName.value = null
  model.value = undefined
  emit('file-selected', props.question.id, null)
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const inputClasses = 'w-full rounded-lg border px-3 py-2 text-sm text-surface-900 dark:text-surface-100 bg-white dark:bg-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors'
const errorBorderClass = 'border-danger-300 dark:border-danger-700'
const normalBorderClass = 'border-surface-300 dark:border-surface-700'
</script>

<template>
  <div>
    <label :for="`q-${question.id}`" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
      {{ question.label }}
      <span v-if="question.required" class="text-danger-500">*</span>
    </label>

    <!-- Short Text -->
    <input
      v-if="question.type === 'short_text'"
      :id="`q-${question.id}`"
      v-model="stringModel"
      type="text"
      :required="question.required"
      :class="[inputClasses, error ? errorBorderClass : normalBorderClass]"
    />

    <!-- Long Text -->
    <textarea
      v-else-if="question.type === 'long_text'"
      :id="`q-${question.id}`"
      v-model="stringModel"
      rows="4"
      :required="question.required"
      :class="[inputClasses, error ? errorBorderClass : normalBorderClass]"
    />

    <!-- Single Select -->
    <select
      v-else-if="question.type === 'single_select'"
      :id="`q-${question.id}`"
      v-model="stringModel"
      :required="question.required"
      :class="[inputClasses, 'bg-white dark:bg-surface-900', error ? errorBorderClass : normalBorderClass]"
    >
      <option value="" disabled>Select an option…</option>
      <option v-for="opt in question.options" :key="opt" :value="opt">
        {{ opt }}
      </option>
    </select>

    <!-- Multi Select (checkboxes) -->
    <div v-else-if="question.type === 'multi_select'" class="space-y-2 mt-1">
      <label
        v-for="opt in question.options"
        :key="opt"
        class="flex items-center gap-2 cursor-pointer"
      >
        <input
          type="checkbox"
          :checked="isOptionSelected(opt)"
          class="size-4 rounded border-surface-300 dark:border-surface-700 text-brand-600 focus:ring-brand-500"
          @change="toggleMultiOption(opt)"
        />
        <span class="text-sm text-surface-700 dark:text-surface-300">{{ opt }}</span>
      </label>
    </div>

    <!-- Number -->
    <input
      v-else-if="question.type === 'number'"
      :id="`q-${question.id}`"
      v-model="numberModel"
      type="number"
      :required="question.required"
      :class="[inputClasses, error ? errorBorderClass : normalBorderClass]"
    />

    <!-- Date -->
    <input
      v-else-if="question.type === 'date'"
      :id="`q-${question.id}`"
      v-model="stringModel"
      type="date"
      :required="question.required"
      :class="[inputClasses, error ? errorBorderClass : normalBorderClass]"
    />

    <!-- URL -->
    <input
      v-else-if="question.type === 'url'"
      :id="`q-${question.id}`"
      v-model="stringModel"
      type="url"
      placeholder="https://…"
      :required="question.required"
      :class="[inputClasses, error ? errorBorderClass : normalBorderClass]"
    />

    <!-- Checkbox (boolean) -->
    <label v-else-if="question.type === 'checkbox'" class="flex items-center gap-2 mt-1 cursor-pointer">
      <input
        :id="`q-${question.id}`"
        v-model="booleanModel"
        type="checkbox"
        class="size-4 rounded border-surface-300 dark:border-surface-700 text-brand-600 focus:ring-brand-500"
      />
      <span class="text-sm text-surface-700 dark:text-surface-300">Yes</span>
    </label>

    <!-- File Upload -->
    <div v-else-if="question.type === 'file_upload'" class="mt-1">
      <input
        ref="fileInputRef"
        type="file"
        :accept="acceptedFileTypes"
        class="hidden"
        @change="handleFileChange"
      />

      <!-- No file selected -->
      <button
        v-if="!selectedFileName"
        type="button"
        class="flex items-center gap-2 rounded-lg border border-dashed px-4 py-3 text-sm transition-colors w-full justify-center"
        :class="error ? 'border-danger-300 dark:border-danger-700 text-danger-600 dark:text-danger-400' : 'border-surface-300 dark:border-surface-700 text-surface-500 dark:text-surface-400 hover:border-brand-400 dark:hover:border-brand-600 hover:text-brand-600 dark:hover:text-brand-400'"
        @click="fileInputRef?.click()"
      >
        <Upload class="size-4" />
        Choose file (PDF, DOC, DOCX — max 10 MB)
      </button>

      <!-- File selected -->
      <div
        v-else
        class="flex items-center justify-between rounded-lg border px-4 py-2.5 text-sm"
        :class="error ? 'border-danger-300 dark:border-danger-700' : 'border-surface-300 dark:border-surface-700'"
      >
        <span class="text-surface-700 dark:text-surface-300 truncate mr-2">{{ selectedFileName }}</span>
        <button
          type="button"
          class="shrink-0 rounded p-0.5 text-surface-400 hover:text-danger-600 transition-colors"
          @click="clearFile"
        >
          <X class="size-4" />
        </button>
      </div>
    </div>

    <!-- Help text -->
    <p v-if="question.description" class="mt-1 text-xs text-surface-400">
      {{ question.description }}
    </p>

    <!-- Error message -->
    <p v-if="error" class="mt-1 text-xs text-danger-600 dark:text-danger-400">{{ error }}</p>
  </div>
</template>
