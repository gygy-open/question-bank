<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'
import FloatingChatWidget from '~/components/chat/FloatingChatWidget.vue'
import { toast } from 'vue-sonner'
import { useLocalStorage, useSessionStorage } from '@vueuse/core'

const { fetchUser, token, user } = useAuth()
const { state: updateState, check: checkUpdate } = useUpdateCheck()
const { init: initSubjectContext } = useSubjectContext()
const ignoredVersion = useLocalStorage('ignored-update-version', '')
const hasPrompted = useSessionStorage('update-prompted', false)

onMounted(async () => {
  if (token.value) {
    await fetchUser()
    await initSubjectContext()
  }
  // Updating is a server-side action (an admin runs the new installer on the
  // server), so only prompt administrators — not every LAN client.
  if (!user.value?.is_superuser) return
  await checkUpdate()
  
  const latest = updateState.value.latest
  if (updateState.value.hasUpdate && latest !== ignoredVersion.value && !hasPrompted.value) {
    hasPrompted.value = true
    toast.info(`发现新版本 v${latest}`, {
      description: `当前 v${updateState.value.current} · 请在服务器上运行新版安装程序更新`,
      action: {
        label: '下载新版',
        onClick: () => window.open(updateState.value.releaseUrl, '_blank'),
      },
      cancel: {
        label: '忽略此版',
        onClick: () => {
          ignoredVersion.value = latest
        }
      }
    })
  }
})
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <slot />
    </SidebarInset>
    <FloatingChatWidget />
  </SidebarProvider>
</template>
