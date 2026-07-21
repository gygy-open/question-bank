<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'
import { toast } from 'vue-sonner'

const { fetchUser, token, user } = useAuth()
const { state: updateState, check: checkUpdate } = useUpdateCheck()

onMounted(async () => {
  if (token.value) {
    await fetchUser()
  }
  // Updating is a server-side action (an admin runs the new installer on the
  // server), so only prompt administrators — not every LAN client.
  if (!user.value?.is_superuser) return
  await checkUpdate()
  if (updateState.value.hasUpdate) {
    toast.info(`发现新版本 v${updateState.value.latest}`, {
      description: `当前 v${updateState.value.current} · 请在服务器上运行新版安装程序更新`,
      action: {
        label: '下载新版',
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
