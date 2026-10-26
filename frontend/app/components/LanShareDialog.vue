<script setup lang="ts">
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SidebarMenuItem, SidebarMenuButton } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Wifi, Copy, Check } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'

const { t } = useI18n()

interface NetworkInfo {
  lan_share: boolean
  port: number
  host_ip: string | null
  lan_url: string | null
  lan_hostname: string | null
  lan_hostname_url: string | null
}

const { $api } = useNuxtApp()

const info = ref<NetworkInfo | null>(null)
const open = ref(false)

const fetchInfo = async () => {
  try {
    info.value = await $api<NetworkInfo>('/system/network')
  } catch (e) {
    // 局域网信息属于可选展示，失败时静默降级（例如服务器版无此概念）
    info.value = null
  }
}

onMounted(fetchInfo)

const { copy, copied, isSupported } = useClipboard({ source: () => info.value?.lan_url || '' })
</script>

<template>
  <SidebarMenuItem v-if="info?.lan_share && info.lan_url">
    <SidebarMenuButton :tooltip="t('lanShare.tooltip')" @click="open = true">
      <Wifi class="text-primary" />
      <span>{{ t('lanShare.menu') }}</span>
    </SidebarMenuButton>

    <Dialog v-model:open="open">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{{ t('lanShare.title') }}</DialogTitle>
          <DialogDescription>
            {{ t('lanShare.description') }}
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="flex items-center gap-2">
            <code
              class="flex-1 truncate rounded-md bg-muted px-3 py-2 text-center text-lg font-semibold tracking-wide">
              {{ info.lan_url }}
            </code>
            <Button v-if="isSupported" size="icon" variant="outline" :title="copied ? t('common.copied') : t('lanShare.copy')"
              @click="copy()">
              <Check v-if="copied" class="size-4 text-green-600" />
              <Copy v-else class="size-4" />
            </Button>
          </div>

          <div v-if="info.lan_hostname_url" class="flex items-center gap-2">
            <code class="flex-1 truncate rounded-md bg-muted px-3 py-2 text-center text-sm text-muted-foreground">
              {{ info.lan_hostname_url }}
            </code>
            <Button v-if="isSupported" size="icon" variant="outline" :title="t('lanShare.copy')"
              @click="copy(info.lan_hostname_url!)">
              <Copy class="size-4" />
            </Button>
          </div>

          <ul class="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li><i18n-t scope="global" keypath="lanShare.tips.sameWifi"><template #em><strong>{{ t('lanShare.tips.sameWifiEm') }}</strong></template></i18n-t></li>
            <li><i18n-t scope="global" keypath="lanShare.tips.ownAccount"><template #em><strong>{{ t('lanShare.tips.ownAccountEm') }}</strong></template></i18n-t></li>
            <li><i18n-t scope="global" keypath="lanShare.tips.keepRunning"><template #em><strong>{{ t('lanShare.tips.keepRunningEm') }}</strong></template></i18n-t></li>
            <li>{{ t('lanShare.tips.ipChange') }}</li>
            <li v-if="info.lan_hostname_url">{{ t('lanShare.tips.hostnameAndroid') }}</li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  </SidebarMenuItem>
</template>
