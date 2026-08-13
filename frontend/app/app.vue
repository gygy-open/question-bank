<script setup lang="ts">
import { Toaster } from '~/components/ui/sonner'
</script>

<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtLayout>
      <NuxtPage keepalive />
    </NuxtLayout>
    <Toaster />
  </div>
</template>
