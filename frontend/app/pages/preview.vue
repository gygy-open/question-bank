<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { renderAsync } from 'docx-preview'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import { Loader2, FileWarning } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

definePageMeta({
  layout: false
})

const route = useRoute()
const fileUrl = ref('')
const fileType = ref<'docx' | 'md' | 'unknown'>('unknown')
const loading = ref(true)
const error = ref('')
const docxContainer = ref<HTMLElement | null>(null)
const mdContent = ref('')

const loadFile = async () => {
  const url = route.query.url as string
  if (!url) {
    error.value = '未提供文件 URL'
    loading.value = false
    return
  }

  fileUrl.value = url
  loading.value = true
  error.value = ''
  mdContent.value = ''

  // Determine type from extension
  const lowerUrl = url.toLowerCase()
  if (lowerUrl.endsWith('.docx')) {
    fileType.value = 'docx'
  } else if (lowerUrl.endsWith('.md')) {
    fileType.value = 'md'
  } else {
    fileType.value = 'unknown'
    error.value = '不支持的文件格式'
    loading.value = false
    return
  }

  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`Failed to load file: ${res.statusText}`)

    if (fileType.value === 'docx') {
      const blob = await res.blob()
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
      mdContent.value = await res.text()
    }
  } catch (e: any) {
    console.error(e)
    error.value = e.message || '加载文件失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadFile()
})

watch(() => route.query.url, () => {
  loadFile()
})
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-3 flex items-center justify-between sticky top-0 z-10 shadow-sm">
      <div class="flex items-center gap-2">
        <h1 class="font-medium text-lg truncate max-w-md" :title="fileUrl">
          文件预览: {{ fileUrl.split('/').pop() }}
        </h1>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" as-child>
          <a :href="fileUrl" download>下载文件</a>
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
