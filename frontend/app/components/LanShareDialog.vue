<script setup lang="ts">
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SidebarMenuItem, SidebarMenuButton } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Wifi, Copy, Check } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'

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
    <SidebarMenuButton tooltip="局域网共享已开启，点击查看访问地址" @click="open = true">
      <Wifi class="text-primary" />
      <span>共享访问地址</span>
    </SidebarMenuButton>

    <Dialog v-model:open="open">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>局域网访问地址</DialogTitle>
          <DialogDescription>
            同一 WiFi / 局域网下的手机或电脑，在浏览器打开下面的地址即可访问本题库。
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="flex items-center gap-2">
            <code
              class="flex-1 truncate rounded-md bg-muted px-3 py-2 text-center text-lg font-semibold tracking-wide">
              {{ info.lan_url }}
            </code>
            <Button v-if="isSupported" size="icon" variant="outline" :title="copied ? '已复制' : '复制地址'"
              @click="copy()">
              <Check v-if="copied" class="size-4 text-green-600" />
              <Copy v-else class="size-4" />
            </Button>
          </div>

          <div v-if="info.lan_hostname_url" class="flex items-center gap-2">
            <code class="flex-1 truncate rounded-md bg-muted px-3 py-2 text-center text-sm text-muted-foreground">
              {{ info.lan_hostname_url }}
            </code>
            <Button v-if="isSupported" size="icon" variant="outline" title="复制地址"
              @click="copy(info.lan_hostname_url!)">
              <Copy class="size-4" />
            </Button>
          </div>

          <ul class="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>手机需连接与本机<strong>相同的 WiFi</strong>。</li>
            <li>每位同事用<strong>各自的账号</strong>登录。</li>
            <li>本机<strong>关机或退出应用</strong>后，他人将无法访问。</li>
            <li>若本机 IP 变化（重启后），此地址会随之更新。</li>
            <li v-if="info.lan_hostname_url">更好记的地址可能在安卓手机上无法打开，此时请改用上方 IP 地址。</li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  </SidebarMenuItem>
</template>
