<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Loader2, Plus, Search } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import MaterialCreateDialog from '@/components/materials/MaterialCreateDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { Stimulus, StimulusListItem } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
  selectedId?: number | null
  groupVisibility?: 'public' | 'private'
}>()
const emit = defineEmits<{ 'update:open': [value: boolean], select: [material: Stimulus] }>()
const { listMaterials } = useMaterials()
const keyword = ref('')
const page = ref(1)
const pages = ref(0)
const results = ref<StimulusListItem[]>([])
const loading = ref(false)
const createOpen = ref(false)
let debounce: ReturnType<typeof setTimeout> | undefined

const load = async () => {
  if (!props.subjectId) return
  loading.value = true
  try {
    const response = await listMaterials(props.subjectId, { page: page.value, size: 10, keyword: keyword.value.trim() || undefined })
    results.value = response.items
    pages.value = response.pages
  } finally { loading.value = false }
}
watch(() => props.open, open => { if (open) { page.value = 1; load() } })
watch(keyword, () => { clearTimeout(debounce); debounce = setTimeout(() => { page.value = 1; load() }, 250) })
watch(page, load)
const isIncompatible = (material: StimulusListItem) => props.groupVisibility === 'public' && material.visibility === 'private'
const choose = (material: Stimulus) => {
  if (material.id === props.selectedId || isIncompatible(material)) return
  emit('select', material)
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)"><DialogContent class="max-w-3xl"><DialogHeader><DialogTitle>选择题目材料</DialogTitle><DialogDescription>题目材料本身不可作答，可被多个题组复用。公开题组不能选择私有题目材料。</DialogDescription></DialogHeader>
    <div class="flex gap-2"><div class="relative flex-1"><Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="keyword" class="pl-9" placeholder="搜索内容或来源" /></div><Button variant="outline" @click="createOpen = true"><Plus class="mr-2 size-4" />新建</Button></div>
    <div v-if="loading" class="flex h-80 items-center justify-center"><Loader2 class="size-6 animate-spin" /></div><div v-else class="h-80 space-y-2 overflow-y-auto pr-1"><button v-for="material in results" :key="material.id" type="button" class="w-full border p-3 text-left hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60" :class="material.id === selectedId ? 'border-primary bg-primary/5' : ''" :disabled="material.id === selectedId || isIncompatible(material)" @click="choose(material)"><div class="mb-2 flex flex-wrap gap-2"><Badge variant="outline">#{{ material.id }}</Badge><Badge variant="secondary">{{ material.status }}</Badge><Badge v-if="material.visibility === 'private'" variant="outline">私有</Badge><Badge v-if="material.id === selectedId" variant="outline">已选择</Badge><span class="truncate text-xs text-muted-foreground">{{ material.source }}</span></div><RichContent :content="material.content" class="line-clamp-3 text-sm" /></button><p v-if="results.length === 0" class="py-16 text-center text-sm text-muted-foreground">没有匹配的题目材料</p></div>
    <div class="flex items-center justify-end gap-2"><Button variant="outline" size="icon" :disabled="page <= 1" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button><span class="text-sm text-muted-foreground">{{ page }} / {{ Math.max(pages, 1) }}</span><Button variant="outline" size="icon" :disabled="page >= pages" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button></div>
  </DialogContent></Dialog>
  <MaterialCreateDialog v-model:open="createOpen" :subject-id="subjectId" @created="choose" />
</template>