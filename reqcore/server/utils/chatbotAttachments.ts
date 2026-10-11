/**
 * In-memory store for chatbot file attachments.
 *
 * Files are uploaded once, parsed, and held in memory for a short TTL so
 * the user can reference them across multiple chat turns without re-upload.
 *
 * Keyed by `${orgId}:${userId}:${attachmentId}` so attachments are strictly
 * scoped to a single user inside a single organisation. A user that is a
 * member of multiple orgs cannot retrieve attachments uploaded under a
 * different org's session, even if the attachment id is known.
 * Cleared via TTL eviction or on logout (best-effort).
 */
import type { ChatbotAttachment } from '../../shared/chatbot'

interface StoredAttachment extends ChatbotAttachment {
  userId: string
  orgId: string
  text: string
  expiresAt: number
}

const TTL_MS = 30 * 60 * 1000 // 30 minutes
const MAX_PER_USER = 20

const store = new Map<string, StoredAttachment>()

function key(orgId: string, userId: string, attachmentId: string) {
  return `${orgId}:${userId}:${attachmentId}`
}

function evictExpired() {
  const now = Date.now()
  for (const [k, v] of store) {
    if (v.expiresAt <= now) store.delete(k)
  }
}

export function saveChatbotAttachment(input: {
  userId: string
  orgId: string
  attachment: ChatbotAttachment
  text: string
}): void {
  evictExpired()

  // Enforce a per-(org,user) cap by evicting the oldest entries.
  const userEntries = Array.from(store.entries())
    .filter(([, v]) => v.userId === input.userId && v.orgId === input.orgId)
    .sort((a, b) => a[1].expiresAt - b[1].expiresAt)
  while (userEntries.length >= MAX_PER_USER) {
    const oldest = userEntries.shift()
    if (oldest) store.delete(oldest[0])
  }

  store.set(key(input.orgId, input.userId, input.attachment.id), {
    ...input.attachment,
    userId: input.userId,
    orgId: input.orgId,
    text: input.text,
    expiresAt: Date.now() + TTL_MS,
  })
}

export function getChatbotAttachments(
  orgId: string,
  userId: string,
  ids: string[],
): Array<ChatbotAttachment & { text: string }> {
  evictExpired()
  const out: Array<ChatbotAttachment & { text: string }> = []
  for (const id of ids) {
    const found = store.get(key(orgId, userId, id))
    if (!found) continue
    out.push({
      id: found.id,
      filename: found.filename,
      mimeType: found.mimeType,
      sizeBytes: found.sizeBytes,
      textLength: found.textLength,
      text: found.text,
    })
  }
  return out
}

export function clearChatbotAttachmentsForUser(
  orgId: string,
  userId: string,
): void {
  for (const [k, v] of store) {
    if (v.userId === userId && v.orgId === orgId) store.delete(k)
  }
}
