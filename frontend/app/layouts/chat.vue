<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'

const { fetchUser, token } = useAuth()

onMounted(() => {
  if (token.value) {
    fetchUser()
  }
})
</script>

<template>
  <SidebarProvider
    :style=" {
      '--header-height': 'calc(var(--spacing) * 12)',
    }"
    class="h-svh overflow-hidden"
  >
    <AppSidebar variant="inset" />
    <SidebarInset class="overflow-hidden">
      <slot />
    </SidebarInset>
  </SidebarProvider>
</template>
