<script setup lang="ts">
import { SidebarProvider, SidebarInset } from '~/components/ui/sidebar'
import AppSidebar from '~/components/AppSidebar.vue'
import FloatingChatWidget from '~/components/chat/FloatingChatWidget.vue'
import { toast } from 'vue-sonner'
import { useLocalStorage, useSessionStorage } from '@vueuse/core'

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
    } else {
      // 普通用户仅提示联系管理员
      toast.info(`发现系统新版本 v${latest}`, {
        description: `当前 v${updateState.value.current} · 为了获得更好的体验，请联系管理员进行升级，或忽略此版本。`,
        cancel: {
          label: '我知道了',
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
    <SidebarInset>
      <div
        v-if="showNoSubjectHint"
        class="m-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
      >
        您还没有被分配任何学科，暂时看不到题库内容。请联系管理员在“学科管理 → 成员管理”中为您开通。
      </div>
      <slot />
    </SidebarInset>
    <FloatingChatWidget />
  </SidebarProvider>
</template>
