<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { renderAsync } from 'docx-preview'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import { Loader2, FileWarning } from '@lucide/vue'
import { Button } from '@/components/ui/button'

definePageMeta({
  layout: false
})

const route = useRoute()
const { $api } = useNuxtApp()
const fileName = ref('')
const downloadUrl = ref('')
const fileType = ref<'docx' | 'md' | 'unknown'>('unknown')
const loading = ref(true)
const error = ref('')
const docxContainer = ref<HTMLElement | null>(null)
const mdContent = ref('')

const releaseDownloadUrl = () => {
  if (downloadUrl.value) URL.revokeObjectURL(downloadUrl.value)
  downloadUrl.value = ''
}

const loadFile = async () => {
  const taskId = Number(route.query.task)
  fileName.value = String(route.query.name || '源文件')
  if (!Number.isInteger(taskId) || taskId <= 0) {
    error.value = '未指定导入任务'
    loading.value = false
    return
  }

  loading.value = true
  error.value = ''
  mdContent.value = ''
  releaseDownloadUrl()

  const lowerName = fileName.value.toLowerCase()
  fileType.value = lowerName.endsWith('.docx') ? 'docx' : lowerName.endsWith('.md') ? 'md' : 'unknown'

  try {
    const blob = await $api<Blob>(`/imports/${taskId}/source`, { responseType: 'blob' })
    downloadUrl.value = URL.createObjectURL(blob)

    if (fileType.value === 'docx') {
      await nextTick()
      if (docxContainer.value) {
        await renderAsync(blob, docxContainer.value, docxContainer.value, {
          className: 'docx-viewer',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          experimental: false,
          trimXmlDeclaration: true,
          useBase64URL: false,
          useMathMLPolyfill: false,
          debug: false,
        })
      }
    } else if (fileType.value === 'md') {
      mdContent.value = await blob.text()
    }
  } catch (e: any) {
    console.error(e)
    error.value = e?.statusCode === 404 ? '源文件不存在或无权查看' : (e?.message || '加载文件失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadFile()
})
onBeforeUnmount(releaseDownloadUrl)

watch(() => route.query.task, () => {
  loadFile()
})
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-3 flex items-center justify-between sticky top-0 z-10 shadow-sm">
      <div class="flex items-center gap-2">
        <h1 class="font-medium text-lg truncate max-w-md" :title="fileName">
          文件预览: {{ fileName }}
        </h1>
      </div>
      <div class="flex items-center gap-2">
        <Button v-if="downloadUrl" variant="outline" size="sm" as-child>
          <a :href="downloadUrl" :download="fileName">下载文件</a>
        </Button>
      </div>
    </header>

    <!-- Content -->
    <main class="flex-1 p-6 overflow-auto flex justify-center">
      <div class="w-full max-w-5xl bg-white rounded-lg shadow-sm min-h-[80vh] p-8">
        
        <!-- Loading -->
        <div v-if="loading" class="flex flex-col items-center justify-center h-64 text-muted-foreground">
          <Loader2 class="h-8 w-8 animate-spin mb-2" />
          <p>正在加载文件...</p>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex flex-col items-center justify-center h-64 text-destructive">
          <FileWarning class="h-10 w-10 mb-2" />
          <p>{{ error }}</p>
          <Button variant="link" @click="loadFile" class="mt-2">重试</Button>
        </div>

        <!-- Docx Viewer -->
        <div v-show="!loading && !error && fileType === 'docx'" class="docx-wrapper">
          <div ref="docxContainer"></div>
        </div>

        <!-- Markdown Viewer -->
        <div v-if="!loading && !error && fileType === 'md'" class="prose max-w-none">
          <MarkdownPreview :content="mdContent" />
        </div>

        <div v-if="!loading && !error && fileType === 'unknown'" class="flex flex-col items-center justify-center h-64 text-muted-foreground">
          <FileWarning class="h-10 w-10 mb-2" />
          <p>该格式不支持在线预览，请下载后查看。</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style>
.docx-viewer {
  background: white !important;
  box-shadow: none !important; 
  padding: 0 !important;
}
/* docx-preview creates its own wrapper styles that might conflict, let's reset some */
.docx-wrapper {
  width: 100%;
}
</style>
