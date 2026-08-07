<script setup lang="ts">
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Download, RefreshCw } from '@lucide/vue'
import { toast } from 'vue-sonner'

defineProps<{ isSuperuser?: boolean }>()
const open = defineModel<boolean>('open', { default: false })

const { state: updateState, check: checkUpdate } = useUpdateCheck()

const handleCheckUpdate = async () => {
  await checkUpdate(true)
  if (updateState.value.error) {
    toast.error('检查更新失败', { description: updateState.value.error })
  } else if (updateState.value.hasUpdate) {
    window.open(updateState.value.releaseUrl, '_blank')
  } else {
    toast.success('已是最新版本', { description: `当前版本 v${updateState.value.current}` })
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-sm">
      <DialogHeader>
        <div class="flex items-center gap-3">
          <img src="/logo.svg" alt="题库系统" class="size-8" />
          <DialogTitle>题库系统 Question Bank</DialogTitle>
        </div>
        <DialogDescription>
          当前版本 v{{ updateState.current || '-' }}
        </DialogDescription>
      </DialogHeader>

      <!-- 更新的下载/安装动作仅对管理员开放，避免普通老师误触 -->
      <div v-if="isSuperuser" class="flex items-center justify-between gap-3 rounded-md border p-3">
        <div class="text-sm">
          <p class="font-medium">
            {{ updateState.hasUpdate ? `发现新版本 v${updateState.latest}` : '检查应用更新' }}
          </p>
          <p class="text-muted-foreground text-xs">仅管理员可下载安装新版本</p>
        </div>
        <Button size="sm" variant="outline" @click="handleCheckUpdate">
          <Download v-if="updateState.hasUpdate" class="mr-2 h-4 w-4" />
          <RefreshCw v-else class="mr-2 h-4 w-4" :class="updateState.checking ? 'animate-spin' : ''" />
          {{ updateState.hasUpdate ? '下载安装' : '检查更新' }}
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
