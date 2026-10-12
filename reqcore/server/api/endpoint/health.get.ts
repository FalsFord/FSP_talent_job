import { authorizeEndpoint } from '../../utils/endpointBridge'
export default defineEventHandler((event) => {
  authorizeEndpoint(event)
  return { status: 'ok', provider: 'Reqcore', configured: Boolean(process.env.REQCORE_AI_API_KEY && process.env.REQCORE_AI_MODEL && process.env.REQCORE_AI_PROVIDER) }
})
