import { z } from 'zod'
import { authorizeEndpoint, endpointProvider } from '../../utils/endpointBridge'
import { generateCriteriaFromDescription } from '../../utils/ai/scoring'

export default defineEventHandler(async (event) => {
  authorizeEndpoint(event)
  const body = await readValidatedBody(event, z.object({ title: z.string().min(1).max(200), description: z.string().min(1).max(50000) }).parse)
  const criteria = await generateCriteriaFromDescription(endpointProvider(), body.title,
    body.description + '\nWrite names and descriptions in Russian. Use only job-relevant professional requirements. Do not evaluate personal traits or culture fit. /no_think')
  return { criteria: criteria.filter(c => c.category !== 'culture'), source: 'reqcore_ai' }
})
