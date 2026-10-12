import { z } from 'zod'
import { authorizeEndpoint } from '../../utils/endpointBridge'
import { parseDocument } from '../../utils/resume-parser'
export default defineEventHandler(async (event) => {
  authorizeEndpoint(event)
  const body = await readValidatedBody(event, z.object({ content: z.string().max(14000000), mime: z.string().max(200) }).parse)
  const result = await parseDocument(Buffer.from(body.content, 'base64'), body.mime)
  if (!result?.text) throw createError({ statusCode: 422, statusMessage: 'No readable resume text' })
  return { text: result.text.slice(0, 60000) }
})
