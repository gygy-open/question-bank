<script setup lang="ts">
import { Check, Copy } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { buildMcpSnippets, MCP_KEY_PLACEHOLDER, type McpSnippetId } from '@/lib/mcpClientConfig'

const props = defineProps<{
  url: string
  /** 刚创建的明文 Key;不传则用占位符 */
  apiKey?: string
}>()

const { t } = useI18n()

const authHeader = computed(() => `Bearer ${props.apiKey || MCP_KEY_PLACEHOLDER}`)
const snippets = computed(() => buildMcpSnippets(props.url, props.apiKey))

const snippetClients: { id: McpSnippetId, label: string }[] = [
  { id: 'claudeCode', label: 'Claude Code' },
  { id: 'cursor', label: 'Cursor' },
  { id: 'vscode', label: 'VS Code' },
  { id: 'workbuddy', label: 'WorkBuddy' },
  { id: 'stdio', label: 'Claude Desktop' },
]

const genericRows = computed(() => [
  { id: 'transport', label: t('settings.mcp.guide.transport'), value: 'Streamable HTTP' },
  { id: 'url', label: t('settings.mcp.guide.url'), value: props.url },
  { id: 'header', label: t('settings.mcp.guide.header'), value: `Authorization: ${authHeader.value}` },
])

const { copy, copied, isSupported } = useClipboard({ copiedDuring: 1500 })
const copiedId = ref<string | null>(null)
const copyText = async (id: string, text: string) => {
  await copy(text)
  copiedId.value = id
}
</script>

<template>
  <div class="space-y-3">
    <Tabs default-value="claudeCode">
      <TabsList class="h-auto flex-wrap">
        <TabsTrigger v-for="c in snippetClients" :key="c.id" :value="c.id">{{ c.label }}</TabsTrigger>
        <TabsTrigger value="generic">{{ t('settings.mcp.guide.generic') }}</TabsTrigger>
      </TabsList>

      <TabsContent v-for="c in snippetClients" :key="c.id" :value="c.id" class="space-y-2">
        <p class="text-sm text-muted-foreground">{{ t(`settings.mcp.guide.${c.id}`) }}</p>
        <div class="relative">
          <pre class="overflow-x-auto rounded-md bg-muted p-3 pr-12 text-xs leading-relaxed"><code>{{ snippets[c.id] }}</code></pre>
          <Button
            v-if="isSupported"
            size="icon"
            variant="ghost"
            class="absolute right-1.5 top-1.5 size-8"
            :title="t('common.copy')"
            @click="copyText(c.id, snippets[c.id])"
          >
            <Check v-if="copied && copiedId === c.id" class="size-4 text-green-600" />
            <Copy v-else class="size-4" />
          </Button>
        </div>
      </TabsContent>

      <TabsContent value="generic">
        <dl class="divide-y rounded-md border text-sm">
          <div v-for="row in genericRows" :key="row.id" class="flex items-center gap-3 px-3 py-2">
            <dt class="w-24 shrink-0 text-muted-foreground">{{ row.label }}</dt>
            <dd class="min-w-0 flex-1 truncate font-mono text-xs">{{ row.value }}</dd>
            <Button
              v-if="isSupported"
              size="icon"
              variant="ghost"
              class="size-7"
              :title="t('common.copy')"
              @click="copyText(row.id, row.value)"
            >
              <Check v-if="copied && copiedId === row.id" class="size-3.5 text-green-600" />
              <Copy v-else class="size-3.5" />
            </Button>
          </div>
        </dl>
      </TabsContent>
    </Tabs>

    <p v-if="!apiKey" class="text-xs text-muted-foreground">
      {{ t('settings.mcp.guide.replaceKey', { placeholder: MCP_KEY_PLACEHOLDER }) }}
    </p>
  </div>
</template>
