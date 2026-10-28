<script setup lang="ts">
import { Check, Copy, KeyRound, Loader2, Plus, ShieldAlert, Trash2 } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'
import { toast } from 'vue-sonner'
import type { ApiKey, ApiKeyAdmin, McpInfo } from '~/types/api-key'
import { apiErrorMessage } from '~/composables/useAIConfigApi'
import { formatDateTime } from '@/lib/locale'
import { formatRelativeTime } from '@/lib/utils'
import ConfirmDialog from '~/components/ai/ConfirmDialog.vue'
import ApiKeyCreateDialog from '~/components/mcp/ApiKeyCreateDialog.vue'
import McpClientGuide from '~/components/mcp/McpClientGuide.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

interface NetworkInfo {
  lan_share: boolean
  lan_url: string | null
  lan_hostname_url: string | null
}

const { t } = useI18n()
const { $api } = useNuxtApp()
const { isAdmin } = usePermissions()

const info = ref<McpInfo | null>(null)
const network = ref<NetworkInfo | null>(null)
const keys = ref<ApiKey[]>([])
const allKeys = ref<ApiKeyAdmin[]>([])
const loading = ref(true)
const toggling = ref(false)
const createOpen = ref(false)
const confirmRef = ref<InstanceType<typeof ConfirmDialog> | null>(null)

const origin = ref('')
onMounted(() => { origin.value = window.location.origin })

const path = computed(() => info.value?.path ?? '/api/mcp')
const endpointUrl = computed(() => `${origin.value}${path.value}`)

/** lan_url 形如 http://192.168.1.5:8000/,拼上 MCP 路径 */
const withPath = (base: string | null | undefined) => (base ? base.replace(/\/+$/, '') + path.value : null)

const endpoints = computed(() => {
  const list = [{ id: 'current', label: t('settings.mcp.endpoint.current'), url: endpointUrl.value }]
  if (network.value?.lan_share) {
    const lan = withPath(network.value.lan_url)
    const host = withPath(network.value.lan_hostname_url)
    if (lan && lan !== endpointUrl.value) list.push({ id: 'lan', label: t('settings.mcp.endpoint.lan'), url: lan })
    if (host && host !== endpointUrl.value) list.push({ id: 'host', label: t('settings.mcp.endpoint.lanHostname'), url: host })
  }
  return list
})

const fetchKeys = async () => {
  keys.value = await $api<ApiKey[]>('/api-keys')
}

const fetchAllKeys = async () => {
  if (!isAdmin.value) return
  allKeys.value = await $api<ApiKeyAdmin[]>('/api-keys/all')
}

const fetchData = async () => {
  try {
    const [mcpInfo] = await Promise.all([
      $api<McpInfo>('/api-keys/mcp-info'),
      fetchKeys(),
      fetchAllKeys(),
    ])
    info.value = mcpInfo
  } catch (e) {
    toast.error(t('settings.mcp.loadFailed'), { description: apiErrorMessage(e) })
  } finally {
    loading.value = false
  }
  try {
    network.value = await $api<NetworkInfo>('/system/network')
  } catch {
    // 局域网信息只是附加展示,失败时静默降级
    network.value = null
  }
}

onMounted(fetchData)
watch(isAdmin, (admin) => { if (admin) fetchAllKeys().catch(() => {}) })

const onToggle = async (enabled: boolean) => {
  toggling.value = true
  try {
    info.value = await $api<McpInfo>('/api-keys/mcp-settings', { method: 'PUT', body: { enabled } })
    toast.success(enabled ? t('settings.mcp.status.enabledToast') : t('settings.mcp.status.disabledToast'))
  } catch (e) {
    toast.error(t('common.operationFailed'), { description: apiErrorMessage(e) })
  } finally {
    toggling.value = false
  }
}

const onCreated = async () => {
  await Promise.all([fetchKeys(), fetchAllKeys()]).catch(() => {})
}

const revoke = async (key: ApiKey, asAdmin: boolean) => {
  const result = await confirmRef.value?.ask({
    title: t('settings.mcp.keys.revokeTitle', { name: key.name }),
    description: t('settings.mcp.keys.revokeDescription'),
    confirmLabel: t('settings.mcp.keys.revoke'),
    destructive: true,
  })
  if (result !== 'confirm') return
  try {
    await $api(asAdmin ? `/api-keys/all/${key.id}` : `/api-keys/${key.id}`, { method: 'DELETE' })
    toast.success(t('settings.mcp.keys.revoked'))
    await Promise.all([fetchKeys(), fetchAllKeys()])
  } catch (e) {
    toast.error(t('common.operationFailed'), { description: apiErrorMessage(e) })
  }
}

const lastUsed = (k: ApiKey) => (k.last_used_at ? formatRelativeTime(k.last_used_at) : t('settings.mcp.keys.neverUsed'))
// 后端返回 UTC naive 时间
const createdAt = (k: ApiKey) => formatDateTime(k.created_at.endsWith('Z') ? k.created_at : `${k.created_at}Z`)

const { copy, copied, isSupported } = useClipboard({ copiedDuring: 1500 })
const copiedUrl = ref<string | null>(null)
const copyUrl = async (url: string) => {
  await copy(url)
  copiedUrl.value = url
}
</script>

<template>
  <div v-if="loading" class="flex justify-center py-12">
    <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
  </div>

  <div v-else class="space-y-10">
    <!-- 服务状态 -->
    <section class="space-y-4">
      <Alert v-if="info && !info.enabled" variant="destructive">
        <ShieldAlert class="h-4 w-4" />
        <AlertTitle>{{ t('settings.mcp.status.disabledTitle') }}</AlertTitle>
        <AlertDescription>{{ t('settings.mcp.status.disabledHint') }}</AlertDescription>
      </Alert>
      <Card v-if="isAdmin && info">
        <CardContent class="flex items-center justify-between gap-4 pt-6">
          <div class="space-y-0.5">
            <Label class="text-base">{{ t('settings.mcp.status.toggleLabel') }}</Label>
            <p class="text-sm text-muted-foreground">{{ t('settings.mcp.status.toggleHint') }}</p>
          </div>
          <Switch :model-value="info.enabled" :disabled="toggling" @update:model-value="onToggle" />
        </CardContent>
      </Card>
    </section>

    <!-- 接入地址 -->
    <section>
      <div class="mb-3">
        <h3 class="text-lg font-semibold">{{ t('settings.mcp.endpoint.title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('settings.mcp.endpoint.description') }}</p>
      </div>
      <div class="space-y-2">
        <div v-for="ep in endpoints" :key="ep.id" class="flex items-center gap-2">
          <span class="w-28 shrink-0 text-sm text-muted-foreground">{{ ep.label }}</span>
          <code class="min-w-0 flex-1 truncate rounded-md bg-muted px-3 py-2 font-mono text-sm">{{ ep.url }}</code>
          <Button v-if="isSupported" size="icon" variant="outline" :title="t('common.copy')" @click="copyUrl(ep.url)">
            <Check v-if="copied && copiedUrl === ep.url" class="size-4 text-green-600" />
            <Copy v-else class="size-4" />
          </Button>
        </div>
        <p v-if="endpoints.length > 1" class="text-xs text-muted-foreground">{{ t('settings.mcp.endpoint.lanHint') }}</p>
      </div>
    </section>

    <!-- 我的 Key -->
    <section>
      <div class="mb-3 flex items-end justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold">{{ t('settings.mcp.keys.title') }}</h3>
          <p class="text-sm text-muted-foreground">{{ t('settings.mcp.keys.description') }}</p>
        </div>
        <Button v-if="keys.length" class="shrink-0" @click="createOpen = true">
          <Plus class="mr-2 h-4 w-4" />{{ t('settings.mcp.keys.create') }}
        </Button>
      </div>

      <Empty v-if="!keys.length" class="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon"><KeyRound /></EmptyMedia>
          <EmptyTitle>{{ t('settings.mcp.keys.emptyTitle') }}</EmptyTitle>
          <EmptyDescription>{{ t('settings.mcp.keys.emptyDescription') }}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant="outline" @click="createOpen = true">
            <Plus class="mr-2 h-4 w-4" />{{ t('settings.mcp.keys.create') }}
          </Button>
        </EmptyContent>
      </Empty>

      <div v-else class="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ t('settings.mcp.keys.name') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.key') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.createdAt') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.lastUsed') }}</TableHead>
              <TableHead class="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="k in keys" :key="k.id">
              <TableCell class="font-medium">{{ k.name }}</TableCell>
              <TableCell class="font-mono text-xs text-muted-foreground">{{ k.prefix }}…</TableCell>
              <TableCell class="text-sm text-muted-foreground">{{ createdAt(k) }}</TableCell>
              <TableCell class="text-sm text-muted-foreground">{{ lastUsed(k) }}</TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" class="text-destructive" :title="t('settings.mcp.keys.revoke')" @click="revoke(k, false)">
                  <Trash2 class="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </section>

    <!-- 客户端配置 -->
    <section>
      <div class="mb-3">
        <h3 class="text-lg font-semibold">{{ t('settings.mcp.guide.title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('settings.mcp.guide.description') }}</p>
      </div>
      <McpClientGuide :url="endpointUrl" />
    </section>

    <!-- 管理员:所有 Key -->
    <section v-if="isAdmin">
      <div class="mb-3">
        <h3 class="text-lg font-semibold">{{ t('settings.mcp.admin.title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('settings.mcp.admin.description') }}</p>
      </div>
      <p v-if="!allKeys.length" class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        {{ t('settings.mcp.admin.empty') }}
      </p>
      <div v-else class="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ t('settings.mcp.keys.owner') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.name') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.key') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.createdAt') }}</TableHead>
              <TableHead>{{ t('settings.mcp.keys.lastUsed') }}</TableHead>
              <TableHead class="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="k in allKeys" :key="k.id">
              <TableCell>{{ k.full_name || k.username }}</TableCell>
              <TableCell class="font-medium">{{ k.name }}</TableCell>
              <TableCell class="font-mono text-xs text-muted-foreground">{{ k.prefix }}…</TableCell>
              <TableCell class="text-sm text-muted-foreground">{{ createdAt(k) }}</TableCell>
              <TableCell class="text-sm text-muted-foreground">{{ lastUsed(k) }}</TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" class="text-destructive" :title="t('settings.mcp.keys.revoke')" @click="revoke(k, true)">
                  <Trash2 class="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </section>

    <ApiKeyCreateDialog v-model:open="createOpen" :url="endpointUrl" @created="onCreated" />
    <ConfirmDialog ref="confirmRef" />
  </div>
</template>
