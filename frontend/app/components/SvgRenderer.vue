<script setup lang="ts">
import { ref, computed } from 'vue'
import { Code, Eye, Download, Check, Copy } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@vueuse/core'

const props = defineProps<{
  code: string
}>()

const showCode = ref(false)
const { copy, copied } = useClipboard()

const svgContent = computed(() => {
    return props.code.trim()
})

const downloadSvg = () => {
  const blob = new Blob([svgContent.value], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `image-${Date.now()}.svg`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const copyCode = () => {
    copy(props.code)
}
</script>

<template>
  <div class="my-4 border rounded-md overflow-hidden bg-background">
    <div class="flex items-center justify-between px-3 py-2 bg-muted/50 border-b">
      <span class="text-xs font-medium text-muted-foreground">SVG Preview</span>
      <div class="flex gap-1">
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="showCode = !showCode" :title="showCode ? '预览' : '查看代码'">
          <Eye v-if="showCode" class="w-3 h-3" />
          <Code v-else class="w-3 h-3" />
        </Button>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="copyCode" title="复制 SVG 代码">
            <Check v-if="copied" class="w-3 h-3 text-green-500" />
            <Copy v-else class="w-3 h-3" />
        </Button>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="downloadSvg" title="下载 SVG">
          <Download class="w-3 h-3" />
        </Button>
      </div>
    </div>
    
    <div class="p-4 flex justify-center items-center min-h-[150px] bg-muted/10 relative">
      <!-- Transparency Grid Background -->
      <div class="absolute inset-0 opacity-20 pointer-events-none" 
           style="background-image: radial-gradient(#888 1px, transparent 1px); background-size: 10px 10px;">
      </div>
      
      <div v-if="!showCode" v-html="svgContent" class="max-w-full overflow-auto z-10"></div>
      <pre v-else class="text-xs overflow-auto max-h-[300px] p-2 bg-muted rounded w-full z-10 whitespace-pre-wrap break-all"><code>{{ code }}</code></pre>
    </div>
  </div>
</template>
