<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { AlertCircle, BookOpen, FileCode, FileText, FolderOpen, Image as ImageIcon, Loader2, Upload, X } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import StructuredTemplateGuideDialog from '@/components/StructuredTemplateGuideDialog.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { zipFolder } from '@/lib/zipFolder'
import type { ImportMethod, ImportMode, ImportTaskItem } from '@/composables/useImportQueue'

const props = defineProps<{
  open: boolean
  initialFiles?: File[]
  initialText?: string
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [items: ImportTaskItem[]]
}>()

const { t } = useI18n()
const { $api } = useNuxtApp()
const { user } = useAuth()
// 学科是全局上下文:导入到当前学科,不在表单里单独选择。
const { currentSubjectId, currentSubject } = useSubjectContext()

const ACCEPT = '.docx,.md,.markdown,.txt,.zip,image/*'
// 与后端 structured_parser 的宽松匹配规则保持一致（全角/半角括号 + 别名）。
const STRUCTURED_TAG_PATTERN = /[【\[]\s*(题目|题干|question|title)\s*[】\]]/i

// 记住解析方式与是否直接入库;「由 AI 补全答案」会消耗额度,不记忆,每次默认使用文档中的答案。
const prefs = useLocalStorage('qb-import-prefs', {
  method: 'auto' as ImportMethod,
  autoCommit: false,
})
const mode = ref<ImportMode>('extract')

const source = ref<'file' | 'text'>('file')
const files = ref<File[]>([])
const text = ref('')
const subjectId = computed(() => currentSubjectId.value)
const submitting = ref(false)
const showGuide = ref(false)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const markdownPreviews = ref<Record<string, string>>({})
const imagePreviews = ref<Record<string, string>>({})

const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`

const addFiles = (picked: Iterable<File>) => {
  const known = new Set(files.value.map(fileKey))
  for (const file of picked) {
    const key = fileKey(file)
    if (known.has(key)) continue
    known.add(key)
    files.value.push(file)
    if (file.type.startsWith('image/')) {
      imagePreviews.value[key] = URL.createObjectURL(file)
    } else if (/\.(md|markdown|txt)$/i.test(file.name)) {
      file.text().then((content) => { markdownPreviews.value[key] = content })
    }
  }
}

const removeFile = (file: File) => {
  const key = fileKey(file)
  files.value = files.value.filter((item) => fileKey(item) !== key)
  if (imagePreviews.value[key]) URL.revokeObjectURL(imagePreviews.value[key])
  delete imagePreviews.value[key]
  delete markdownPreviews.value[key]
}

const reset = () => {
  for (const url of Object.values(imagePreviews.value)) URL.revokeObjectURL(url)
  files.value = []
  text.value = ''
  imagePreviews.value = {}
  markdownPreviews.value = {}
  source.value = 'file'
}

watch(() => props.open, (open) => {
  if (!open) return
  reset()
  mode.value = 'extract'
  if (props.initialFiles?.length) addFiles(props.initialFiles)
  if (props.initialText) {
    text.value = props.initialText
    source.value = 'text'
  }
}, { immediate: true })

const onPickFiles = (e: Event) => {
  const input = e.target as HTMLInputElement
  if (input.files) addFiles(Array.from(input.files))
  input.value = ''
}

const onPickFolder = async (e: Event) => {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  try {
    addFiles([await zipFolder(input.files, 'markdown-folder.zip')])
  } catch (err: any) {
    toast.error(t('imports.newDialog.zipFailed', { error: String(err?.message ?? err) }))
  } finally {
    input.value = ''
  }
}

const onDrop = (e: DragEvent) => {
  isDragging.value = false
  const dropped = e.dataTransfer?.files
  if (dropped?.length) {
    addFiles(Array.from(dropped))
    source.value = 'file'
  }
}

const onPaste = (e: ClipboardEvent) => {
  const items = Array.from(e.clipboardData?.items ?? [])
  const images = items
    .filter((item) => item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => !!file)
  if (!images.length) return
  e.preventDefault()
  addFiles(images.map((blob, i) => new File([blob], `pasted-image-${Date.now()}-${i}.png`, { type: blob.type })))
  source.value = 'file'
}

const canSubmit = computed(() => source.value === 'file' ? files.value.length > 0 : text.value.trim().length > 0)
const mayUseAi = computed(() => prefs.value.method !== 'structured'
  || (source.value === 'file' && files.value.some((f) => f.type.startsWith('image/'))))

// 选了「按标签解析」但文本里完全没有【题目】标签时提前提示,避免空跑一遍。
const tagWarning = computed(() => {
  if (prefs.value.method !== 'structured') return false
  const texts = source.value === 'text'
    ? [text.value]
    : files.value.map((f) => markdownPreviews.value[fileKey(f)]).filter((v): v is string => !!v)
  return texts.some((value) => value.trim() && !STRUCTURED_TAG_PATTERN.test(value))
})

// 非阻塞的就绪检查:未配置向量模型 / 当前学科知识点未建索引时,导入不会自动匹配知识点。
const embeddingConfigured = ref(true)
const kpVectorized = ref(true)
const isSuperuser = computed(() => !!user.value?.is_superuser)
watch([() => props.open, subjectId], async ([open]) => {
  if (!open || !subjectId.value) return
  try {
    const res = await $api<{ embedding_configured: boolean; kp_vectorized: boolean }>(
      '/knowledge-points/embedding-status',
      { query: { subject_id: subjectId.value } },
    )
    embeddingConfigured.value = res.embedding_configured
    kpVectorized.value = res.kp_vectorized
  } catch {
    embeddingConfigured.value = true
    kpVectorized.value = true
  }
})

const fileIcon = (file: File) => {
  if (file.type.startsWith('image/')) return ImageIcon
  if (file.name.toLowerCase().endsWith('.docx')) return FileText
  return FileCode
}

const submit = async () => {
  if (!canSubmit.value) {
    toast.error(t('imports.newDialog.empty'))
    return
  }
  if (!subjectId.value) {
    toast.error(t('apiErrors.import_task.subject_required'))
    return
  }
  submitting.value = true
  const options = {
    // 不调用 AI 时「补全答案」没有意义,按使用文档答案提交。
    mode: mayUseAi.value ? mode.value : 'extract',
    method: prefs.value.method,
    auto_commit: prefs.value.autoCommit,
    subject_id: subjectId.value,
  }
  try {
    let items: ImportTaskItem[]
    if (source.value === 'file') {
      const form = new FormData()
      for (const file of files.value) form.append('files', file)
      const res = await $api<{ items: ImportTaskItem[]; skipped: string[] }>('/imports', {
        method: 'POST',
        body: form,
        query: options,
      })
      items = res.items
      if (res.skipped.length) {
        toast.warning(t('imports.newDialog.skipped', { names: res.skipped.join(t('imports.newDialog.nameSeparator')) }))
      }
    } else {
      items = [await $api<ImportTaskItem>('/imports/text', {
        method: 'POST',
        body: { content: text.value, ...options },
      })]
    }
    toast.success(t('imports.newDialog.created', { count: items.length }))
    emit('created', items)
    emit('update:open', false)
  } catch (e: any) {
    toast.error(getApiErrorDetail(e, e.message))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="(v) => emit('update:open', v)">
    <DialogContent class="flex max-h-[calc(100svh-2rem)] flex-col sm:max-w-xl" @paste="onPaste">
      <DialogHeader>
        <DialogTitle>{{ t('imports.newDialog.title') }}</DialogTitle>
        <DialogDescription>{{ currentSubject ? t('imports.newDialog.description', { subject: currentSubject.name }) : t('apiErrors.import_task.subject_required') }}</DialogDescription>
      </DialogHeader>

      <!-- 内容超出窗口高度时只滚动中间部分,标题和按钮保持可见 -->
      <div class="-mx-6 min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-1">
      <Tabs v-model="source" class="w-full">
        <TabsList class="grid w-full grid-cols-2">
          <TabsTrigger value="file">{{ t('imports.newDialog.tabs.file') }}</TabsTrigger>
          <TabsTrigger value="text">{{ t('imports.newDialog.tabs.text') }}</TabsTrigger>
        </TabsList>

        <TabsContent value="file" class="mt-3 space-y-2">
          <div
            class="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors"
            :class="isDragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDrop"
          >
            <Upload class="h-6 w-6 text-muted-foreground" />
            <p class="text-sm text-muted-foreground">
              <i18n-t scope="global" keypath="imports.newDialog.dropOrPick">
                <template #pick>
                  <button type="button" class="font-medium text-primary underline-offset-4 hover:underline" @click="fileInput?.click()">
                    {{ t('imports.newDialog.pick') }}
                  </button>
                </template>
              </i18n-t>
            </p>
            <p class="text-xs text-muted-foreground">
              <i18n-t scope="global" keypath="imports.newDialog.folderHint">
                <template #folder>
                  <button type="button" class="underline hover:text-primary" @click="folderInput?.click()">
                    <FolderOpen class="mr-0.5 inline h-3 w-3" />{{ t('imports.newDialog.pickFolder') }}
                  </button>
                </template>
              </i18n-t>
            </p>
            <input ref="fileInput" type="file" class="hidden" multiple :accept="ACCEPT" @change="onPickFiles" />
            <input ref="folderInput" type="file" class="hidden" webkitdirectory directory multiple @change="onPickFolder" />
          </div>

          <ul v-if="files.length" class="space-y-1">
            <li v-for="file in files" :key="fileKey(file)" class="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
              <img v-if="imagePreviews[fileKey(file)]" :src="imagePreviews[fileKey(file)]" alt="" class="h-8 w-8 shrink-0 rounded object-cover" />
              <component :is="fileIcon(file)" v-else class="h-4 w-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0 flex-1 truncate" :title="file.name">{{ file.name }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ (file.size / 1024 / 1024).toFixed(2) }} MB</span>
              <Button variant="ghost" size="icon" class="h-6 w-6 shrink-0" :title="t('imports.newDialog.remove')" @click="removeFile(file)">
                <X class="h-3.5 w-3.5" />
              </Button>
            </li>
          </ul>
        </TabsContent>

        <TabsContent value="text" class="mt-3">
          <Textarea v-model="text" :placeholder="t('imports.newDialog.textPlaceholder')" class="min-h-[180px] font-mono text-sm" />
        </TabsContent>
      </Tabs>

      <div class="grid gap-4">
        <div class="grid gap-1.5">
          <div class="flex items-center justify-between">
            <Label>{{ t('imports.newDialog.method') }}</Label>
            <Button variant="link" size="sm" class="h-auto p-0 text-xs" @click="showGuide = true">
              <BookOpen class="mr-1 h-3 w-3" />{{ t('imports.newDialog.viewTagGuide') }}
            </Button>
          </div>
          <Select v-model="prefs.method">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{{ t('imports.newDialog.methodAuto') }}</SelectItem>
              <SelectItem value="ai">{{ t('imports.newDialog.methodAi') }}</SelectItem>
              <SelectItem value="structured">{{ t('imports.newDialog.methodStructured') }}</SelectItem>
            </SelectContent>
          </Select>
          <p class="text-xs text-muted-foreground">
            {{ prefs.method === 'auto' ? t('imports.newDialog.methodAutoHint', { tag: '【题目】' }) : prefs.method === 'ai' ? t('imports.newDialog.methodAiHint') : t('imports.newDialog.methodStructuredHint', { tags: '【题目】【答案】' }) }}
          </p>
        </div>
        <!-- 「由 AI 补全答案」只对 AI 识别生效;纯标签解析时不显示 -->
        <div v-if="mayUseAi" class="grid gap-1.5">
          <Label>{{ t('imports.newDialog.answers') }}</Label>
          <RadioGroup v-model="mode" class="gap-2">
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <RadioGroupItem value="extract" />{{ t('imports.newDialog.answersExtract') }}
            </label>
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <RadioGroupItem value="solve" />{{ t('imports.newDialog.answersSolve') }}
            </label>
          </RadioGroup>
          <p v-if="prefs.method === 'auto'" class="text-xs text-muted-foreground">{{ t('imports.newDialog.answersAutoHint') }}</p>
        </div>

        <label class="flex cursor-pointer items-start justify-between gap-4">
          <span class="grid gap-0.5">
            <span class="text-sm font-medium">{{ t('imports.newDialog.autoCommit') }}</span>
            <span class="text-xs text-muted-foreground">{{ t('imports.newDialog.autoCommitHint') }}</span>
          </span>
          <Switch :model-value="prefs.autoCommit" @update:model-value="(v: boolean) => prefs.autoCommit = v" />
        </label>

        <Alert v-if="tagWarning">
          <AlertCircle class="h-4 w-4" />
          <AlertDescription>
            {{ t('importSmart.alerts.tagMissing', { tag: '【题目】' }) }}
            <button type="button" class="ml-1 font-medium underline" @click="showGuide = true">{{ t('imports.newDialog.viewTagGuide') }}</button>
          </AlertDescription>
        </Alert>
        <Alert v-else-if="mayUseAi && !embeddingConfigured">
          <AlertCircle class="h-4 w-4" />
          <AlertDescription>
            <i18n-t scope="global" keypath="importSmart.alerts.embeddingNotConfigured">
              <template #link><NuxtLink to="/settings" class="font-medium underline">{{ t('nav.systemSettings') }}</NuxtLink></template>
            </i18n-t>
          </AlertDescription>
        </Alert>
        <Alert v-else-if="mayUseAi && !kpVectorized">
          <AlertCircle class="h-4 w-4" />
          <AlertDescription>
            <i18n-t v-if="isSuperuser" scope="global" keypath="importSmart.alerts.kpNotVectorizedAdmin">
              <template #link><NuxtLink to="/knowledge-points" class="font-medium underline">{{ t('nav.knowledgePoints') }}</NuxtLink></template>
            </i18n-t>
            <template v-else>{{ t('importSmart.alerts.kpNotVectorized') }}</template>
          </AlertDescription>
        </Alert>
      </div>

      </div>

      <DialogFooter>
        <Button variant="outline" :disabled="submitting" @click="emit('update:open', false)">{{ t('common.cancel') }}</Button>
        <Button :disabled="submitting || !canSubmit || !subjectId" @click="submit">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          {{ submitting ? t('imports.newDialog.submitting') : t('imports.newDialog.submit') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <StructuredTemplateGuideDialog :open="showGuide" @update:open="(v) => showGuide = v" />
</template>
