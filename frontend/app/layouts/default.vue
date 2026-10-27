<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'
import ChatSidePanel from '~/components/chat/ChatSidePanel.vue'
import { toast } from 'vue-sonner'
import { useLocalStorage, useSessionStorage } from '@vueuse/core'

const { t } = useI18n()
const { fetchUser, token, user } = useAuth()
const { hasSubjects } = useSubjectContext()
const { state: updateState, check: checkUpdate } = useUpdateCheck()
const ignoredVersion = useLocalStorage('ignored-update-version', '')
const hasPrompted = useSessionStorage('update-prompted', false)

// 普通用户未被分配任何学科时的空状态提示(管理员不受限)。
const showNoSubjectHint = computed(
  () => !!token.value && !user.value?.is_superuser && !hasSubjects.value,
)

onMounted(async () => {
  // 学科上下文已由 auth.global.ts 中间件在进入本布局前初始化完毕
  if (token.value) {
    await fetchUser()
  }
  // 让所有登录用户都能检查更新，以便进行对应权限的弹窗提示
  await checkUpdate()
  
  const latest = updateState.value.latest
  if (updateState.value.hasUpdate && latest !== ignoredVersion.value && !hasPrompted.value) {
    hasPrompted.value = true
    
    if (user.value?.is_superuser) {
      // 管理员提示更新步骤与下载
      toast.info(t('layout.update.adminTitle', { version: latest }), {
        description: t('layout.update.adminDescription', { current: updateState.value.current }),
        action: {
          label: t('layout.update.download'),
          onClick: () => window.open(updateState.value.releaseUrl, '_blank'),
        },
        cancel: {
          label: t('layout.update.ignore'),
          onClick: () => {
            ignoredVersion.value = latest
          }
        }
      })
    } else {
      // 普通用户仅提示联系管理员
      toast.info(t('layout.update.userTitle', { version: latest }), {
        description: t('layout.update.userDescription', { current: updateState.value.current }),
        cancel: {
          label: t('layout.update.acknowledge'),
          onClick: () => {
            ignoredVersion.value = latest
          }
        }
      })
    }
  }
})
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset class="min-w-0">
      <div
        v-if="showNoSubjectHint"
        class="m-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
      >
        {{ t('layout.noSubjectHint') }}
      </div>
      <slot />
    </SidebarInset>
    <ChatSidePanel />
  </SidebarProvider>
</template>
