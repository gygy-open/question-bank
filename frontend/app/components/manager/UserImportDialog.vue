<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Upload, Download, FileSpreadsheet, FileCheck, X, Loader2,
  CheckCircle2, XCircle, Copy, BookOpen,
} from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Label } from '@/components/ui/label'
import { toast } from 'vue-sonner'
import type { UserImportResult } from '@/types'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'imported'): void
}>()

const { $api } = useNuxtApp()

type Step = 'upload' | 'importing' | 'result'
const step = ref<Step>('upload')
const selectedFile = ref<File | null>(null)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const result = ref<UserImportResult | null>(null)

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    step.value = 'upload'
    selectedFile.value = null
    result.value = null
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
    const blob = await $api('/users/import-template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(blob as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'users_template.xlsx'
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e: any) {
    toast.error('下载模板失败: ' + (e.data?.detail || e.message))
  }
}

const runImport = async () => {
  if (!selectedFile.value) return
  step.value = 'importing'
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  try {
    result.value = await $api<UserImportResult>('/users/import', {
      method: 'POST',
      body: formData,
    })
    step.value = 'result'
    if (result.value.created > 0) {
      emit('imported')
    }
  } catch (e: any) {
    result.value = {
      status: 'failed', created: 0, failed: 0, total: 0,
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
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="w-[95vw] sm:max-w-[640px] max-h-[90vh] overflow-y-auto">
      <!-- ===== Step 1: Upload ===== -->
      <template v-if="step === 'upload'">
        <DialogHeader>
          <DialogTitle>批量导入用户</DialogTitle>
          <DialogDescription>通过 Excel 一次性创建多个用户账号</DialogDescription>
        </DialogHeader>

        <Alert>
          <BookOpen class="h-4 w-4" />
          <AlertTitle>使用说明</AlertTitle>
          <AlertDescription>
            <ol class="list-decimal list-inside space-y-0.5 text-sm">
              <li>下载 Excel 模板，查看格式示例</li>
              <li>填写用户名、姓名、密码（管理员列可选）</li>
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
                    <p class="font-medium">users_template.xlsx</p>
                    <p class="text-muted-foreground mt-1">模板列：用户名(必填)、姓名(必填)、密码(必填，≥6位)、管理员(可选，填“是”)</p>
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
          <Button :disabled="!selectedFile" @click="runImport">开始导入</Button>
        </DialogFooter>
      </template>

      <!-- ===== Step 2: Importing ===== -->
      <template v-else-if="step === 'importing'">
        <DialogHeader>
          <DialogTitle>批量导入用户</DialogTitle>
          <DialogDescription>正在处理，请稍候…</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col items-center justify-center py-12 gap-3">
          <Loader2 class="w-8 h-8 animate-spin text-primary" />
          <p class="text-sm text-muted-foreground">正在导入用户…</p>
        </div>
      </template>

      <!-- ===== Step 3: Result ===== -->
      <template v-else>
        <DialogHeader>
          <DialogTitle>导入结果</DialogTitle>
          <DialogDescription>
            共 {{ result?.total ?? 0 }} 行，成功 {{ result?.created ?? 0 }} 个，失败 {{ result?.failed ?? 0 }} 个
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <CheckCircle2 v-if="result?.status === 'success'" class="w-8 h-8 text-green-600" />
            <XCircle v-else-if="result?.status === 'failed'" class="w-8 h-8 text-destructive" />
            <CheckCircle2 v-else class="w-8 h-8 text-amber-500" />
            <div class="text-sm">
              <p class="font-medium">
                {{ result?.status === 'success' ? '全部导入成功' : result?.status === 'failed' ? '导入失败' : '部分导入成功' }}
              </p>
              <p class="text-muted-foreground">成功创建 {{ result?.created ?? 0 }} 个用户</p>
            </div>
          </div>

          <div v-if="result?.errors?.length" class="border rounded-md">
            <div class="flex items-center justify-between px-3 py-2 border-b bg-muted/40">
              <span class="text-sm font-medium">失败明细（{{ result.errors.length }}）</span>
              <Button variant="ghost" size="sm" @click="copyErrors">
                <Copy class="w-4 h-4 mr-1" />复制
              </Button>
            </div>
            <div class="max-h-60 overflow-y-auto divide-y">
              <div v-for="(err, i) in result.errors" :key="i" class="flex gap-3 px-3 py-2 text-sm">
                <span class="text-muted-foreground shrink-0">{{ err.row > 0 ? `第 ${err.row} 行` : '文件' }}</span>
                <span class="text-destructive">{{ err.message }}</span>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button variant="outline" @click="backToUpload">继续导入</Button>
          <Button @click="close">完成</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>
</template>
