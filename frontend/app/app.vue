<script setup lang="ts">
import { Toaster } from '~/components/ui/sonner'
import FloatingChatWidget from '~/components/chat/FloatingChatWidget.vue'

const route = useRoute()
// Hide the assistant on unauthenticated / setup screens.
const showAssistant = computed(() => !['/login', '/setup', '/preview'].some(p => route.path.startsWith(p)))
</script>

<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtLayout>
      <NuxtPage keepalive />
    </NuxtLayout>
    <FloatingChatWidget v-if="showAssistant" />
    <Toaster />
  </div>
</template>
