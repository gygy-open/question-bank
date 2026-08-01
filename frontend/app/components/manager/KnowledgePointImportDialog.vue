<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Upload, Download, FileSpreadsheet, FileCheck, X, Info, AlertTriangle,
  Loader2, CheckCircle2, XCircle, Circle, ArrowRight, ArrowLeft, Copy, Lightbulb, BookOpen,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'vue-sonner'
import type { KPImportResult, KPImportPreflight } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
  subjectName: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'imported'): void
}>()

const { $api } = useNuxtApp()

type Step = 'upload' | 'settings' | 'importing' | 'result'
const step = ref<Step>('upload')
const importMode = ref<'incremental' | 'rebuild'>('incremental')
const selectedFile = ref<File | null>(null)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const showDangerConfirm = ref(false)
const confirmInput = ref('')
const preflight = ref<KPImportPreflight | null>(null)

const result = ref<KPImportResult | null>(null)

// Reset everything whenever the dialog is (re)opened.
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    step.value = 'upload'
    importMode.value = 'incremental'
    selectedFile.value = null
    result.value = null
    confirmInput.value = ''
    preflight.value = null
  }
})

const close = () => emit('update:open', false)

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const validateAndSet = (f: File): boolean => {
  if (!f.name.toLowerCase().endsWith('.xlsx')) {
    toast.error('文件格式不正确，请上传 .xlsx 文件')
    return false
  }
  if (f.size > 5 * 1024 * 1024) {
    toast.error('文件过大，请确保文件小于 5MB')
    return false
  }
  selectedFile.value = f
  return true
}

const handleFileChange = (e: Event) => {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    validateAndSet(target.files[0])
  }
}

const handleDrop = (e: DragEvent) => {
  isDragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) validateAndSet(f)
}

const triggerFileInput = () => fileInput.value?.click()
const clearFile = () => { selectedFile.value = null }

const downloadTemplate = async () => {
  try {
    const blob = await $api('/knowledge-points/import-template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(blob as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'knowledge_points_template.xlsx'
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e: any) {
    toast.error('下载模板失败: ' + (e.data?.detail || e.message))
  }
}

const goToSettings = () => {
  if (!selectedFile.value) return
  step.value = 'settings'
}

const confirmImport = async () => {
  if (importMode.value === 'rebuild') {
    // Fetch impact assessment before showing the danger confirmation.
    if (props.subjectId) {
      try {
        preflight.value = await $api<KPImportPreflight>('/knowledge-points/import-preflight', {
          query: { subject_id: props.subjectId },
        })
      } catch {
        preflight.value = null
      }
    }
    confirmInput.value = ''
    showDangerConfirm.value = true
    return
  }
  await runImport()
}

const executeRebuild = async () => {
  showDangerConfirm.value = false
  await runImport()
}

const runImport = async () => {
  if (!selectedFile.value) return
  step.value = 'importing'
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('mode', importMode.value)
  try {
    result.value = await $api<KPImportResult>('/knowledge-points/import', {
      method: 'POST',
      body: formData,
    })
    step.value = 'result'
    if (result.value.status !== 'failed') {
      emit('imported')
    }
  } catch (e: any) {
    result.value = {
      status: 'failed', mode: importMode.value, created: 0, skipped: 0, failed: 0,
      total: 0, duration: 0, vector_synced: false,
      errors: [{ row: 0, message: e.data?.detail || e.message || '导入失败' }],
    }
    step.value = 'result'
  }
}

const copyErrors = () => {
  if (!result.value) return
  const text = result.value.errors.map(err => `第 ${err.row} 行: ${err.message}`).join('\n')
  navigator.clipboard.writeText(text)
  toast.success('已复制错误信息')
}

const backToUpload = () => { step.value = 'upload' }

const modeName = computed(() => importMode.value === 'incremental' ? '增量新增' : '清空重建')
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="w-[95vw] sm:max-w-[640px] max-h-[90vh] overflow-y-auto">
      <!-- ===== Step 1: Upload ===== -->
      <template v-if="step === 'upload'">
        <DialogHeader>
          <DialogTitle>批量导入知识点</DialogTitle>
          <DialogDescription>步骤 1 / 2：准备导入文件</DialogDescription>
        </DialogHeader>

        <Alert>
          <BookOpen class="h-4 w-4" />
          <AlertTitle>使用说明</AlertTitle>
          <AlertDescription>
            <p class="mb-1">本功能用于批量创建知识点树，支持五级嵌套。请按以下步骤操作：</p>
            <ol class="list-decimal list-inside space-y-0.5 text-sm">
              <li>下载 Excel 模板，查看格式示例</li>
              <li>在模板中填写知识点数据</li>
              <li>上传填写好的文件</li>
            </ol>
          </AlertDescription>
        </Alert>

        <div class="space-y-4">
          <div>
            <Label class="text-sm font-medium">1. 下载并填写模板</Label>
            <Card class="mt-2 bg-muted/30">
              <CardContent class="pt-4">
                <div class="flex items-start gap-3">
                  <FileSpreadsheet class="w-9 h-9 text-green-600 shrink-0" />
                  <div class="flex-1 text-sm">
                    <p class="font-medium">knowledge_points_template.xlsx</p>
                    <p class="text-muted-foreground mt-1">模板列：学科名称(必填)、一级目录(必填)、二级~五级目录(可选)</p>
                  </div>
                </div>
                <Button variant="outline" class="mt-3 w-full" @click="downloadTemplate">
                  <Download class="w-4 h-4 mr-2" />下载 Excel 模板
                </Button>
              </CardContent>
            </Card>
          </div>

          <div>
            <Label class="text-sm font-medium">2. 上传填写好的文件</Label>
            <div
              class="mt-2 border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors"
              :class="isDragging ? 'border-primary bg-primary/5' : 'hover:border-primary/50'"
              role="button"
              tabindex="0"
              @click="triggerFileInput"
              @keydown.enter="triggerFileInput"
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @drop.prevent="handleDrop"
            >
              <Upload class="w-7 h-7 mx-auto text-muted-foreground mb-2" />
              <p class="text-sm font-medium">点击选择文件 或 拖拽文件到此处</p>
              <p class="text-xs text-muted-foreground mt-1">仅支持 .xlsx 格式，最大 5MB</p>
              <input ref="fileInput" type="file" accept=".xlsx" class="hidden" @change="handleFileChange" />
            </div>

            <div v-if="selectedFile" class="mt-3 flex items-center gap-2 p-3 bg-muted rounded-md">
              <FileCheck class="w-4 h-4 text-green-600 shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium truncate">{{ selectedFile.name }}</p>
                <p class="text-xs text-muted-foreground">{{ formatFileSize(selectedFile.size) }}</p>
              </div>
              <Button variant="ghost" size="sm" @click="clearFile"><X class="w-4 h-4" /></Button>
            </div>
          </div>
        </div>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button variant="outline" @click="close">取消</Button>
          <Button :disabled="!selectedFile" @click="goToSettings">
            下一步<ArrowRight class="w-4 h-4 ml-2" />
          </Button>
        </DialogFooter>
      </template>

      <!-- ===== Step 2: Settings ===== -->
      <template v-else-if="step === 'settings'">
        <DialogHeader>
          <DialogTitle>批量导入知识点</DialogTitle>
          <DialogDescription>步骤 2 / 2：确认导入设置</DialogDescription>
        </DialogHeader>

        <div class="flex items-center gap-2 text-sm p-2 bg-muted rounded-md">
          <FileCheck class="w-4 h-4 text-green-600" />
          <span class="truncate">导入文件：{{ selectedFile?.name }}</span>
        </div>

        <div class="space-y-3">
          <Label class="text-sm font-medium">选择导入模式</Label>

          <Card
            class="cursor-pointer transition-all"
            :class="importMode === 'incremental' ? 'border-primary ring-2 ring-primary/20' : ''"
            @click="importMode = 'incremental'"
          >
            <CardContent class="pt-4">
              <p class="font-medium flex items-center gap-2 mb-2">
                <span class="w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center"
                  :class="importMode === 'incremental' ? 'border-primary' : 'border-muted-foreground'">
                  <span v-if="importMode === 'incremental'" class="w-1.5 h-1.5 rounded-full bg-primary" />
                </span>
                增量新增 <Badge variant="secondary" class="text-xs">推荐</Badge>
              </p>
              <div class="text-xs text-muted-foreground space-y-1 pl-5">
                <p>• 已存在的知识点（相同学科、父节点、名称）自动跳过</p>
                <p>• 新知识点正常创建，<strong>不影响已有题目的知识点关联</strong></p>
                <p class="text-foreground/70">适用：日常新增、修正数据后重新导入</p>
              </div>
            </CardContent>
          </Card>

          <Card
            class="cursor-pointer transition-all"
            :class="importMode === 'rebuild' ? 'border-destructive ring-2 ring-destructive/20' : ''"
            @click="importMode = 'rebuild'"
          >
            <CardContent class="pt-4">
              <p class="font-medium flex items-center gap-2 mb-2">
                <span class="w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center"
                  :class="importMode === 'rebuild' ? 'border-destructive' : 'border-muted-foreground'">
                  <span v-if="importMode === 'rebuild'" class="w-1.5 h-1.5 rounded-full bg-destructive" />
                </span>
                清空重建 <Badge variant="destructive" class="text-xs">谨慎使用</Badge>
              </p>
              <div class="text-xs text-muted-foreground space-y-1 pl-5">
                <p>• 先删除文件中涉及学科的<strong>所有</strong>知识点，再导入新数据</p>
                <p class="text-orange-600">⚠️ 已关联的题目将失去知识点标签（题目本身保留）</p>
                <p class="text-orange-600">⚠️ 此操作不可撤销</p>
                <p class="text-foreground/70">适用：完全重构知识点体系</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button variant="outline" @click="backToUpload">
            <ArrowLeft class="w-4 h-4 mr-2" />上一步
          </Button>
          <Button variant="outline" @click="close">取消</Button>
          <Button :variant="importMode === 'rebuild' ? 'destructive' : 'default'" @click="confirmImport">
            <Upload class="w-4 h-4 mr-2" />开始导入
          </Button>
        </DialogFooter>
      </template>

      <!-- ===== Step 3: Importing ===== -->
      <template v-else-if="step === 'importing'">
        <DialogHeader>
          <DialogTitle>正在导入知识点...</DialogTitle>
        </DialogHeader>
        <div class="py-10 text-center space-y-4">
          <Loader2 class="w-12 h-12 animate-spin text-primary mx-auto" />
          <p class="text-sm text-muted-foreground">正在解析并写入知识点，请勿关闭此窗口</p>
        </div>
      </template>

      <!-- ===== Step 4: Result ===== -->
      <template v-else-if="step === 'result' && result">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <CheckCircle2 v-if="result.status === 'success'" class="w-5 h-5 text-green-600" />
            <AlertTriangle v-else-if="result.status === 'partial'" class="w-5 h-5 text-orange-600" />
            <XCircle v-else class="w-5 h-5 text-red-600" />
            <span v-if="result.status === 'success'">导入完成</span>
            <span v-else-if="result.status === 'partial'">导入完成（含警告）</span>
            <span v-else>导入失败</span>
          </DialogTitle>
        </DialogHeader>

        <Card v-if="result.status !== 'failed'" class="bg-muted/30">
          <CardContent class="pt-4 text-sm space-y-2">
            <div class="flex items-center gap-2">
              <CheckCircle2 class="w-4 h-4 text-green-600" />
              <span>成功创建：<strong>{{ result.created }}</strong> 个知识点</span>
            </div>
            <div v-if="result.skipped > 0" class="flex items-center gap-2">
              <Circle class="w-4 h-4 text-yellow-600" />
              <span>跳过重复：<strong>{{ result.skipped }}</strong> 个</span>
            </div>
            <div v-if="result.failed > 0" class="flex items-center gap-2">
              <XCircle class="w-4 h-4 text-red-600" />
              <span>失败：<strong>{{ result.failed }}</strong> 个</span>
            </div>
            <p class="text-xs text-muted-foreground pt-1">
              模式：{{ modeName }} · 耗时 {{ result.duration }}s ·
              {{ result.vector_synced ? '已同步向量索引' : '未配置向量模型，可稍后手动重建' }}
            </p>
          </CardContent>
        </Card>

        <Alert v-if="result.errors.length > 0" variant="destructive">
          <XCircle class="h-4 w-4" />
          <AlertTitle>失败详情</AlertTitle>
          <AlertDescription>
            <div class="text-xs font-mono space-y-0.5 mt-1 max-h-40 overflow-y-auto">
              <div v-for="err in result.errors" :key="`${err.row}-${err.message}`">
                <span v-if="err.row > 0">第 {{ err.row }} 行: </span>{{ err.message }}
              </div>
            </div>
            <Button variant="outline" size="sm" class="mt-2" @click="copyErrors">
              <Copy class="w-3.5 h-3.5 mr-1.5" />复制错误信息
            </Button>
          </AlertDescription>
        </Alert>

        <Alert v-if="result.status === 'partial'">
          <Lightbulb class="h-4 w-4" />
          <AlertDescription class="text-xs">
            修正 Excel 中对应行的数据后重新上传即可，已成功的数据会被自动跳过。
          </AlertDescription>
        </Alert>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button v-if="result.status === 'failed'" variant="outline" @click="backToUpload">返回修改</Button>
          <Button @click="close">完成</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>

  <!-- ===== Danger confirmation (rebuild) ===== -->
  <Dialog :open="showDangerConfirm" @update:open="showDangerConfirm = $event">
    <DialogContent class="w-[95vw] sm:max-w-[480px]">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2 text-destructive">
          <AlertTriangle class="w-5 h-5" />确认清空重建
        </DialogTitle>
        <DialogDescription>您即将执行不可撤销的危险操作，请仔细确认。</DialogDescription>
      </DialogHeader>

      <Alert variant="destructive">
        <AlertTriangle class="h-4 w-4" />
        <AlertTitle>数据影响评估</AlertTitle>
        <AlertDescription class="text-xs space-y-1 mt-1">
          <p v-if="preflight">• 学科「{{ preflight.subject_name }}」现有 <strong>{{ preflight.existing_count }}</strong> 个知识点将被删除</p>
          <p v-if="preflight">• <strong>{{ preflight.affected_questions }}</strong> 道题目将失去知识点标签</p>
          <p>• 题目内容本身不会被删除</p>
          <p>• 此操作不可撤销，无法回滚</p>
        </AlertDescription>
      </Alert>

      <div>
        <Label class="text-sm">请输入学科名称「{{ subjectName }}」以确认：</Label>
        <Input v-model="confirmInput" class="mt-2 font-mono" :placeholder="subjectName"
          @keyup.enter="confirmInput === subjectName && executeRebuild()" />
      </div>

      <DialogFooter class="flex-col sm:flex-row gap-2">
        <Button variant="outline" @click="showDangerConfirm = false">取消</Button>
        <Button variant="destructive" :disabled="confirmInput !== subjectName" @click="executeRebuild">
          确认删除并导入
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
