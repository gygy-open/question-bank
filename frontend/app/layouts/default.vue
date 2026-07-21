<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'
import { toast } from 'vue-sonner'

const { fetchUser, token } = useAuth()
const { state: updateState, check: checkUpdate } = useUpdateCheck()

onMounted(async () => {
  if (token.value) {
    fetchUser()
  }
  await checkUpdate()
  if (updateState.value.hasUpdate) {
    toast.info(`发现新版本 v${updateState.value.latest}`, {
      description: `当前版本 v${updateState.value.current}`,
      action: {
        label: '查看更新',
        onClick: () => window.open(updateState.value.releaseUrl, '_blank'),
      },
    })
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
