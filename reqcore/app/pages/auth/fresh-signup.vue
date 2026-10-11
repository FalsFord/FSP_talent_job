<script setup lang="ts">
definePageMeta({ layout: 'auth' })

useSeoMeta({ robots: 'noindex, nofollow' })

onMounted(() => {
  // Navigate directly to the server endpoint. It checks the session,
  // signs out via Better Auth's own handler if it's a demo org (which
  // produces the correct Set-Cookie headers), and 302-redirects to
  // /auth/sign-up or /dashboard. Native browser navigation guarantees
  // the Set-Cookie headers are processed as part of following the redirect.
  window.location.replace('/api/auth/demo-fresh-signup')
})
</script>

<template>
  <div class="flex items-center justify-center min-h-[60vh]">
    <p class="text-sm text-surface-500 dark:text-surface-400">Redirecting…</p>
  </div>
</template>
