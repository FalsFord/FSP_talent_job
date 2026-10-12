import { z } from 'zod'

// ─────────────────────────────────────────────
// Document validation schemas & constants
// ─────────────────────────────────────────────

/**
 * MIME types allowed for document upload.
 * Restricts uploads to PDF and Word documents only.
 */
export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
] as const

/** Maximum file size in bytes (10 MB) */
export const MAX_FILE_SIZE = 10 * 1024 * 1024

/** Maximum number of documents per candidate */
export const MAX_DOCUMENTS_PER_CANDIDATE = 20

/**
 * Map of allowed MIME types to their file extensions.
 * Used to derive a safe file extension from the validated MIME type.
 */
export const MIME_TO_EXTENSION: Record<string, string> = {
  'application/pdf': 'pdf',
  'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
}

/** Schema for the document type field (matches the DB enum) */
export const documentTypeSchema = z.enum(['resume', 'cover_letter', 'other'])

/**
 * Sanitize a user-provided filename for safe storage and display.
 * Removes characters that could enable path traversal, XSS, or
 * filesystem-level exploits. Never use raw user-supplied filenames.
 */
export function sanitizeFilename(filename: string): string {
  return filename
    .replace(/[<>:"'\/\\|?*\x00-\x1f]/g, '_') // Replace dangerous chars
    .replace(/\.{2,}/g, '.') // Collapse consecutive dots (path traversal)
    .replace(/^[.\s]+|[.\s]+$/g, '') // Remove leading/trailing dots and spaces
    .slice(0, 255) // Limit length
    || 'unnamed'
}
