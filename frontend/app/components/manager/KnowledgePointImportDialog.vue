<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Upload, Download, FileSpreadsheet, FileCheck, X, Info, AlertTriangle,
  Loader2, CheckCircle2, XCircle, Circle, ArrowRight, ArrowLeft, Copy, Lightbulb, BookOpen,
} from '@lucide/vue'
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

const { t } = useI18n()
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
    toast.error(t('importDialog.invalidFormat'))
    return false
  }
  if (f.size > 5 * 1024 * 1024) {
    toast.error(t('importDialog.fileTooLarge'))
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
    toast.error(t('importDialog.downloadTemplateFailed', { error: e.data?.detail || e.message }))
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
      errors: [{ row: 0, message: e.data?.detail || e.message || t('importDialog.importFailed') }],
    }
    step.value = 'result'
  }
}

const copyErrors = () => {
  if (!result.value) return
  const text = result.value.errors.map(err => t('importDialog.errorLine', { row: err.row, message: err.message })).join('\n')
  navigator.clipboard.writeText(text)
  toast.success(t('importDialog.errorsCopied'))
}

const backToUpload = () => { step.value = 'upload' }

const modeName = computed(() => importMode.value === 'incremental' ? t('kpImport.mode.incremental') : t('kpImport.mode.rebuild'))
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="w-[95vw] sm:max-w-[640px] max-h-[90vh] overflow-y-auto">
      <!-- ===== Step 1: Upload ===== -->
      <template v-if="step === 'upload'">
        <DialogHeader>
          <DialogTitle>{{ t('kpImport.title') }}</DialogTitle>
          <DialogDescription>{{ t('kpImport.step1') }}</DialogDescription>
        </DialogHeader>

        <Alert>
          <BookOpen class="h-4 w-4" />
          <AlertTitle>{{ t('importDialog.instructions') }}</AlertTitle>
          <AlertDescription>
            <p class="mb-1">{{ t('kpImport.intro') }}</p>
            <ol class="list-decimal list-inside space-y-0.5 text-sm">
              <li>{{ t('importDialog.stepDownload') }}</li>
              <li>{{ t('kpImport.steps.fill') }}</li>
              <li>{{ t('importDialog.stepUpload') }}</li>
            </ol>
          </AlertDescription>
        </Alert>

        <div class="space-y-4">
          <div>
            <Label class="text-sm font-medium">{{ t('importDialog.sectionTemplate') }}</Label>
            <Card class="mt-2 bg-muted/30">
              <CardContent class="pt-4">
                <div class="flex items-start gap-3">
                  <FileSpreadsheet class="w-9 h-9 text-green-600 shrink-0" />
                  <div class="flex-1 text-sm">
                    <p class="font-medium">knowledge_points_template.xlsx</p>
                    <p class="text-muted-foreground mt-1">{{ t('kpImport.templateColumns', { subject: t('kpImport.columns.subject'), level1: t('kpImport.columns.level1'), level2: t('kpImport.columns.level2'), level8: t('kpImport.columns.level8') }) }}</p>
                  </div>
                </div>
                <Button variant="outline" class="mt-3 w-full" @click="downloadTemplate">
                  <Download class="w-4 h-4 mr-2" />{{ t('importDialog.downloadTemplate') }}
                </Button>
              </CardContent>
            </Card>
          </div>

          <div>
            <Label class="text-sm font-medium">{{ t('importDialog.sectionUpload') }}</Label>
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
              <p class="text-sm font-medium">{{ t('importDialog.dropHint') }}</p>
              <p class="text-xs text-muted-foreground mt-1">{{ t('importDialog.formatHint') }}</p>
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
          <Button variant="outline" @click="close">{{ t('common.cancel') }}</Button>
          <Button :disabled="!selectedFile" @click="goToSettings">
            {{ t('kpImport.next') }}<ArrowRight class="w-4 h-4 ml-2" />
          </Button>
        </DialogFooter>
      </template>

      <!-- ===== Step 2: Settings ===== -->
      <template v-else-if="step === 'settings'">
        <DialogHeader>
          <DialogTitle>{{ t('kpImport.title') }}</DialogTitle>
          <DialogDescription>{{ t('kpImport.step2') }}</DialogDescription>
        </DialogHeader>

        <div class="flex items-center gap-2 text-sm p-2 bg-muted rounded-md">
          <FileCheck class="w-4 h-4 text-green-600" />
          <span class="truncate">{{ t('kpImport.fileName', { name: selectedFile?.name ?? '' }) }}</span>
        </div>

        <div class="space-y-3">
          <Label class="text-sm font-medium">{{ t('kpImport.selectMode') }}</Label>

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
                {{ t('kpImport.mode.incremental') }} <Badge variant="secondary" class="text-xs">{{ t('kpImport.recommended') }}</Badge>
              </p>
              <div class="text-xs text-muted-foreground space-y-1 pl-5">
                <p>{{ t('kpImport.incremental.skipExisting') }}</p>
                <p><i18n-t scope="global" keypath="kpImport.incremental.createNew" tag="span"><template #em><strong>{{ t('kpImport.incremental.createNewEm') }}</strong></template></i18n-t></p>
                <p class="text-foreground/70">{{ t('kpImport.incremental.useCase') }}</p>
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
                {{ t('kpImport.mode.rebuild') }} <Badge variant="destructive" class="text-xs">{{ t('kpImport.useWithCaution') }}</Badge>
              </p>
              <div class="text-xs text-muted-foreground space-y-1 pl-5">
                <p><i18n-t scope="global" keypath="kpImport.rebuild.deleteAll" tag="span"><template #em><strong>{{ t('kpImport.rebuild.deleteAllEm') }}</strong></template></i18n-t></p>
                <p class="text-orange-600">{{ t('kpImport.rebuild.loseLinks') }}</p>
                <p class="text-orange-600">{{ t('kpImport.rebuild.irreversible') }}</p>
                <p class="text-foreground/70">{{ t('kpImport.rebuild.useCase') }}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button variant="outline" @click="backToUpload">
            <ArrowLeft class="w-4 h-4 mr-2" />{{ t('kpImport.prev') }}
          </Button>
          <Button variant="outline" @click="close">{{ t('common.cancel') }}</Button>
          <Button :variant="importMode === 'rebuild' ? 'destructive' : 'default'" @click="confirmImport">
            <Upload class="w-4 h-4 mr-2" />{{ t('importDialog.start') }}
          </Button>
        </DialogFooter>
      </template>

      <!-- ===== Step 3: Importing ===== -->
      <template v-else-if="step === 'importing'">
        <DialogHeader>
          <DialogTitle>{{ t('kpImport.importingTitle') }}</DialogTitle>
        </DialogHeader>
        <div class="py-10 text-center space-y-4">
          <Loader2 class="w-12 h-12 animate-spin text-primary mx-auto" />
          <p class="text-sm text-muted-foreground">{{ t('kpImport.importingHint') }}</p>
        </div>
      </template>

      <!-- ===== Step 4: Result ===== -->
      <template v-else-if="step === 'result' && result">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <CheckCircle2 v-if="result.status === 'success'" class="w-5 h-5 text-green-600" />
            <AlertTriangle v-else-if="result.status === 'partial'" class="w-5 h-5 text-orange-600" />
            <XCircle v-else class="w-5 h-5 text-red-600" />
            <span v-if="result.status === 'success'">{{ t('kpImport.status.success') }}</span>
            <span v-else-if="result.status === 'partial'">{{ t('kpImport.status.partial') }}</span>
            <span v-else>{{ t('importDialog.importFailed') }}</span>
          </DialogTitle>
        </DialogHeader>

        <Card v-if="result.status !== 'failed'" class="bg-muted/30">
          <CardContent class="pt-4 text-sm space-y-2">
            <div class="flex items-center gap-2">
              <CheckCircle2 class="w-4 h-4 text-green-600" />
              <i18n-t scope="global" keypath="kpImport.result.created" tag="span"><template #count><strong>{{ result.created }}</strong></template></i18n-t>
            </div>
            <div v-if="result.skipped > 0" class="flex items-center gap-2">
              <Circle class="w-4 h-4 text-yellow-600" />
              <i18n-t scope="global" keypath="kpImport.result.skipped" tag="span"><template #count><strong>{{ result.skipped }}</strong></template></i18n-t>
            </div>
            <div v-if="result.failed > 0" class="flex items-center gap-2">
              <XCircle class="w-4 h-4 text-red-600" />
              <i18n-t scope="global" keypath="kpImport.result.failed" tag="span"><template #count><strong>{{ result.failed }}</strong></template></i18n-t>
            </div>
            <p class="text-xs text-muted-foreground pt-1">
              {{ t('kpImport.result.meta', { mode: modeName, duration: result.duration }) }} ·
              {{ result.vector_synced ? t('kpImport.result.vectorSynced') : t('kpImport.result.vectorNotConfigured') }}
            </p>
          </CardContent>
        </Card>

        <Alert v-if="result.errors.length > 0" variant="destructive">
          <XCircle class="h-4 w-4" />
          <AlertTitle>{{ t('kpImport.errorDetails') }}</AlertTitle>
          <AlertDescription>
            <div class="text-xs font-mono space-y-0.5 mt-1 max-h-40 overflow-y-auto">
              <div v-for="err in result.errors" :key="`${err.row}-${err.message}`">
                <span v-if="err.row > 0">{{ t('kpImport.rowPrefix', { row: err.row }) }}</span>{{ err.message }}
              </div>
            </div>
            <Button variant="outline" size="sm" class="mt-2" @click="copyErrors">
              <Copy class="w-3.5 h-3.5 mr-1.5" />{{ t('kpImport.copyErrors') }}
            </Button>
          </AlertDescription>
        </Alert>

        <Alert v-if="result.status === 'partial'">
          <Lightbulb class="h-4 w-4" />
          <AlertDescription class="text-xs">
            {{ t('kpImport.partialHint') }}
          </AlertDescription>
        </Alert>

        <DialogFooter class="flex-col sm:flex-row gap-2">
          <Button v-if="result.status === 'failed'" variant="outline" @click="backToUpload">{{ t('kpImport.backToEdit') }}</Button>
          <Button @click="close">{{ t('common.done') }}</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>

  <!-- ===== Danger confirmation (rebuild) ===== -->
  <Dialog :open="showDangerConfirm" @update:open="showDangerConfirm = $event">
    <DialogContent class="w-[95vw] sm:max-w-[480px]">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2 text-destructive">
          <AlertTriangle class="w-5 h-5" />{{ t('kpImport.danger.title') }}
        </DialogTitle>
        <DialogDescription>{{ t('kpImport.danger.description') }}</DialogDescription>
      </DialogHeader>

      <Alert variant="destructive">
        <AlertTriangle class="h-4 w-4" />
        <AlertTitle>{{ t('kpImport.danger.impact') }}</AlertTitle>
        <AlertDescription class="text-xs space-y-1 mt-1">
          <p v-if="preflight"><i18n-t scope="global" keypath="kpImport.danger.existing" tag="span"><template #subject>{{ preflight.subject_name }}</template><template #count><strong>{{ preflight.existing_count }}</strong></template></i18n-t></p>
          <p v-if="preflight"><i18n-t scope="global" keypath="kpImport.danger.affected" tag="span"><template #count><strong>{{ preflight.affected_questions }}</strong></template></i18n-t></p>
          <p>{{ t('kpImport.danger.questionsKept') }}</p>
          <p>{{ t('kpImport.danger.noRollback') }}</p>
        </AlertDescription>
      </Alert>

      <div>
        <Label class="text-sm">{{ t('kpImport.danger.confirmLabel', { name: subjectName }) }}</Label>
        <Input v-model="confirmInput" class="mt-2 font-mono" :placeholder="subjectName"
          @keyup.enter="confirmInput === subjectName && executeRebuild()" />
      </div>

      <DialogFooter class="flex-col sm:flex-row gap-2">
        <Button variant="outline" @click="showDangerConfirm = false">{{ t('common.cancel') }}</Button>
        <Button variant="destructive" :disabled="confirmInput !== subjectName" @click="executeRebuild">
          {{ t('kpImport.danger.confirm') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
