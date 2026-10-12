import { describe, it, expect } from 'vitest'
import { createAiConfigSchema, updateAiConfigSchema } from '../../server/utils/schemas/scoring'

/**
 * Validates the AI config schema accepts all supported providers,
 * especially 'openai_compatible' (issue #130), and rejects SSRF risks.
 *
 * `createAiConfigSchema` requires both `name` and `apiKey` (used in
 * server/api/ai-config/index.post.ts to insert and encrypt the row);
 * `updateAiConfigSchema` makes both optional so PATCH can keep the
 * existing stored key when only metadata changes.
 */
describe('createAiConfigSchema', () => {
  it('accepts openai_compatible provider with baseUrl', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'Local Llama',
      provider: 'openai_compatible',
      model: 'llama-3.1-8b',
      apiKey: 'test-key',
      baseUrl: 'http://localhost:11434/v1',
      maxTokens: 4096,
    })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.baseUrl).toBe('http://localhost:11434/v1')
      expect(result.data.maxTokens).toBe(4096)
    }
  })

  it('accepts openai_compatible without baseUrl', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'Custom',
      provider: 'openai_compatible',
      model: 'custom-model',
      apiKey: 'test-key',
    })

    expect(result.success).toBe(true)
    if (result.success) {
      // baseUrl is nullish — when omitted, the parsed value stays undefined
      expect(result.data.baseUrl).toBeUndefined()
      // maxTokens defaults to 16384 when omitted
      expect(result.data.maxTokens).toBe(16384)
    }
  })

  it('accepts standard openai provider', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'Prod OpenAI',
      provider: 'openai',
      model: 'gpt-4.1-mini',
      apiKey: 'sk-test123',
    })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.isDefaultChatbot).toBe(false)
      expect(result.data.isDefaultAnalysis).toBe(false)
    }
  })

  it('rejects unknown provider', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'Ollama Local',
      provider: 'ollama',
      model: 'llama-3.1',
      apiKey: 'test',
    })

    expect(result.success).toBe(false)
  })

  it('rejects SSRF-risky baseUrl targeting AWS metadata', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'evil',
      provider: 'openai_compatible',
      model: 'test',
      apiKey: 'test',
      baseUrl: 'http://169.254.169.254/latest/meta-data/',
    })

    expect(result.success).toBe(false)
  })

  it('rejects SSRF-risky baseUrl targeting GCP metadata', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'evil',
      provider: 'openai_compatible',
      model: 'test',
      apiKey: 'test',
      baseUrl: 'http://metadata.google.internal/computeMetadata/v1/',
    })

    expect(result.success).toBe(false)
  })

  it('requires name (used by INSERT in index.post.ts)', () => {
    const result = createAiConfigSchema.safeParse({
      provider: 'openai',
      model: 'gpt-4.1-mini',
      apiKey: 'sk-test',
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path[0] === 'name')).toBe(true)
    }
  })

  it('requires apiKey on create (the encrypted value must come from the request)', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'no-key',
      provider: 'openai',
      model: 'gpt-4.1-mini',
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path[0] === 'apiKey')).toBe(true)
    }
  })

  it('trims surrounding whitespace from name', () => {
    const result = createAiConfigSchema.safeParse({
      name: '  Padded  ',
      provider: 'openai',
      model: 'gpt-4',
      apiKey: 'k',
    })

    expect(result.success).toBe(true)
    if (result.success) expect(result.data.name).toBe('Padded')
  })

  it('rejects name longer than 80 characters', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'x'.repeat(81),
      provider: 'openai',
      model: 'gpt-4',
      apiKey: 'k',
    })

    expect(result.success).toBe(false)
  })

  it('rejects maxTokens above the 200000 ceiling', () => {
    const result = createAiConfigSchema.safeParse({
      name: 'huge',
      provider: 'openai',
      model: 'gpt-4',
      apiKey: 'k',
      maxTokens: 200001,
    })

    expect(result.success).toBe(false)
  })
})

describe('updateAiConfigSchema', () => {
  it('allows apiKey to be omitted (so PATCH keeps the stored key)', () => {
    const result = updateAiConfigSchema.safeParse({
      name: 'Renamed',
    })

    expect(result.success).toBe(true)
    if (result.success) expect(result.data.apiKey).toBeUndefined()
  })

  it('still validates apiKey length when provided', () => {
    const result = updateAiConfigSchema.safeParse({
      apiKey: '',
    })

    expect(result.success).toBe(false)
  })

  it('rejects SSRF-risky baseUrl on update too', () => {
    const result = updateAiConfigSchema.safeParse({
      baseUrl: 'http://169.254.169.254/',
    })

    expect(result.success).toBe(false)
  })
})

