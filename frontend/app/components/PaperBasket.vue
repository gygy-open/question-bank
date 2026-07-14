<script setup lang="ts">
import { ref, reactive } from 'vue'
import { usePaperBasket } from '@/composables/usePaperBasket'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ShoppingBasket, X, FileDown, Loader2, Trash2 } from 'lucide-vue-next'
import { useAPI } from '@/composables/useAPI'

const { items, remove, clear } = usePaperBasket()
const isOpen = ref(false)
const isGenerating = ref(false)

const form = reactive({
  title: '',
  format: 'docx',
  include_answer: false,
  include_analysis: false,
  include_explanation: false,
  include_summary: false,
  include_source: false
})

const download = async () => {
  if (!form.title) return
  isGenerating.value = true
  try {
    const { data, error } = await useAPI('/papers/download', {
      method: 'POST',
      body: {
        title: form.title,
        question_ids: items.value.map(i => i.id),
        format: form.format,
        include_answer: form.include_answer,
        include_analysis: form.include_analysis,
        include_explanation: form.include_explanation,
        include_summary: form.include_summary,
        include_source: form.include_source
      },
      responseType: 'blob'
    })
    
    if (data.value) {
      const url = window.URL.createObjectURL(data.value as Blob)
      const link = document.createElement('a')
      link.href = url
      const ext = form.format === 'latex' ? 'zip' : form.format
      link.setAttribute('download', `${form.title}.${ext}`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      isOpen.value = false
      // clear() // Manual clear only
    }
  } catch (e) {
    console.error(e)
  } finally {
    isGenerating.value = false
  }
}
</script>

<template>
  <div v-if="items.length > 0" class="fixed bottom-8 right-8 z-50">
    <Button size="lg" class="rounded-full shadow-lg gap-2" @click="isOpen = true">
      <ShoppingBasket class="h-5 w-5" />
      <span>试题篮 ({{ items.length }})</span>
    </Button>

    <Dialog v-model:open="isOpen">
      <DialogContent class="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>生成试卷</DialogTitle>
        </DialogHeader>
        
        <div class="grid gap-4 py-4">
          <div class="space-y-4 max-h-[300px] overflow-y-auto pr-2">
            <div v-for="item in items" :key="item.id" class="flex items-start justify-between gap-2 p-2 border rounded bg-muted/50">
              <div class="text-sm line-clamp-2 flex-1" v-html="item.content"></div>
              <Button variant="ghost" size="icon" class="h-6 w-6 text-muted-foreground hover:text-destructive" @click="remove(item.id)">
                <X class="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          <div class="grid gap-2">
            <Label>试卷标题</Label>
            <Input v-model="form.title" placeholder="请输入试卷标题" />
          </div>
          
          <div class="grid gap-2">
            <Label>导出格式</Label>
            <Select v-model="form.format">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="docx">Word (.docx)</SelectItem>
                <SelectItem value="latex">LaTeX (带有图片的 .zip 压缩包)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="grid gap-2">
            <Label>导出选项</Label>
            <div class="flex flex-wrap gap-4">
              <div class="flex items-center space-x-2">
                <Checkbox id="include_answer" v-model="form.include_answer" />
                <Label for="include_answer">标准答案</Label>
              </div>
              <div class="flex items-center space-x-2">
                <Checkbox id="include_analysis" v-model="form.include_analysis" />
                <Label for="include_analysis">分析</Label>
              </div>
              <div class="flex items-center space-x-2">
                <Checkbox id="include_explanation" v-model="form.include_explanation" />
                <Label for="include_explanation">解析</Label>
              </div>
              <div class="flex items-center space-x-2">
                <Checkbox id="include_summary" v-model="form.include_summary" />
                <Label for="include_summary">总结</Label>
              </div>
              <div class="flex items-center space-x-2">
                <Checkbox id="include_source" v-model="form.include_source" />
                <Label for="include_source">来源</Label>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter class="sm:justify-between">
          <Button variant="destructive" @click="clear(); isOpen = false" :disabled="items.length === 0">
            <Trash2 class="mr-2 h-4 w-4" />
            清空试题篮
          </Button>
          <div class="flex gap-2">
            <Button variant="outline" @click="isOpen = false">取消</Button>
            <Button @click="download" :disabled="!form.title || isGenerating">
              <Loader2 v-if="isGenerating" class="mr-2 h-4 w-4 animate-spin" />
              <FileDown v-else class="mr-2 h-4 w-4" />
              生成并下载
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
