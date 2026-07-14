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
  >
    <AppSidebar variant="inset" />
    <SidebarInset>
      <slot />
    </SidebarInset>
  </SidebarProvider>
</template>
