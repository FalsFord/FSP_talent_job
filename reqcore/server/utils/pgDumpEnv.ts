/**
 * Variables that pg_dump (and the libpq it links against) actually read.
 * Anything outside this list — application secrets in particular — must not
 * be inherited by the child process so it can never leak through libpq
 * diagnostics or pg_dump's own stderr.
 */
const PG_DUMP_ENV_ALLOWLIST = ['PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'TMPDIR'] as const

/**
 * Build the env object passed to pg_dump. Only PGPASSWORD and a small set
 * of generic system vars are forwarded; everything else from the parent
 * process is dropped so secrets like BETTER_AUTH_SECRET, S3_SECRET_KEY,
 * OAuth client secrets, etc. never reach the child.
 *
 * Exported (rather than inlined in the route handler) so the allowlist can
 * be unit-tested without spawning pg_dump.
 */
export function buildPgDumpEnv(parentEnv: NodeJS.ProcessEnv, password: string): NodeJS.ProcessEnv {
  const childEnv: NodeJS.ProcessEnv = {}
  // Only set PGPASSWORD when non-empty: an empty value can confuse older libpq
  // and overrides ~/.pgpass / trust-auth lookup.
  if (password) childEnv.PGPASSWORD = password
  for (const key of PG_DUMP_ENV_ALLOWLIST) {
    const value = parentEnv[key]
    if (value !== undefined) childEnv[key] = value
  }
  return childEnv
}
