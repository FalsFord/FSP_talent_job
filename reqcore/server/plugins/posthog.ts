/**
 * Nitro plugin: initialise PostHog integrations on startup and shut them
 * down cleanly when the server process closes.
 *
 * – PostHog Node client  (event capture, error tracking)
 * – OpenTelemetry logger (PostHog Logs via OTLP)
 * – Filtered error capture (skips 404s from bot scanners)
 */
export default defineNitroPlugin((nitroApp) => {
  // Start the OpenTelemetry LoggerProvider so structured logs
  // are sent to PostHog's /i/v1/logs endpoint throughout the lifetime
  // of the server process.
  initLoggerProvider()

  // Capture server errors to PostHog, but skip 404 "Page not found" errors
  // which are overwhelmingly bot/vulnerability scanner noise.
  nitroApp.hooks.hook('error', (error) => {
    const statusCode = (error as { statusCode?: number }).statusCode
    if (statusCode === 404) return

    const ph = useServerPostHog()
    if (!ph) return

    ph.captureException(error)
  })

  nitroApp.hooks.hookOnce('close', async () => {
    await Promise.all([
      shutdownServerPostHog(),
      shutdownLoggerProvider(),
    ])
  })
})
