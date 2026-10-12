<script setup lang="ts">
const route = useRoute()

const isBlogRoute = computed(() => /^\/blog(?:\/|$)/.test(route.path))
</script>

<template>
  <div class="layout-default">
    <div v-if="!isBlogRoute" class="fixed right-3 top-3 z-[60]">
      <LanguageSwitcher />
    </div>
    <slot />
  </div>
</template>
