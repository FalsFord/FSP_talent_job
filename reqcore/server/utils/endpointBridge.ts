import { timingSafeEqual } from 'node:crypto'
import { encrypt } from './encryption'
import type { H3Event } from 'h3'
import type { ProviderConfig, SupportedProvider } from './ai/provider'

/** Private EndPoint bridge; never uses browser sessions or accepts client API keys. */
export function authorizeEndpoint(event: H3Event) {
  const supplied = Buffer.from(getHeader(event, 'x-service-token') || '')
  const expected = Buffer.from(process.env.ATS_SERVICE_TOKEN || '')
  if (!expected.length || supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) {
    throw createError({ statusCode: 401, statusMessage: 'Service authentication required' })
  }
}

export function endpointProvider(): ProviderConfig {
  const key = process.env.REQCORE_AI_API_KEY
  const model = process.env.REQCORE_AI_MODEL
  const provider = process.env.REQCORE_AI_PROVIDER
  if (!key || !model || !['openai', 'anthropic', 'google', 'openai_compatible'].includes(provider || '')) {
    throw createError({ statusCode: 503, statusMessage: 'Reqcore AI provider is not configured' })
  }
  return {
    provider: provider as SupportedProvider, model,
    apiKeyEncrypted: encrypt(key, env.BETTER_AUTH_SECRET),
    baseUrl: process.env.REQCORE_AI_BASE_URL || null,
    maxTokens: 3000,
  }
}
