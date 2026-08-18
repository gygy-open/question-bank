<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Input } from '@/components/ui/input'
import { Loader2, Blocks } from '@lucide/vue'
import { useCompositions } from '~/composables/useCompositions'
import type { Composition } from '~/types'

const props = defineProps<{
  active: boolean
  /** 排除当前正在编辑的组稿, 避免自我引用。 */
  excludeId?: number
}>()

const emit = defineEmits<{
  pick: [composition: Composition]
}>()

const { list } = useCompositions()
const { currentSubjectId } = useSubjectContext()

const keyword = ref('')
const loading = ref(false)
const results = ref<Composition[]>([])

const search = useDebounceFn(async () => {
  loading.value = true
  try {
    const data = await list({
      subject_id: currentSubjectId.value,
      keyword: keyword.value || undefined,
      sort: 'updated_desc',
    })
    results.value = data.filter((c) => c.id !== props.excludeId)
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}, 300)

watch(() => props.active, (v) => {
  if (v) {
    keyword.value = ''
    search()
  }
})
watch(keyword, search)
</script>

<template>
  <div>
    <Input v-model="keyword" placeholder="搜索文档..." class="h-8 text-sm mb-2" autofocus />
    <div v-if="loading" class="flex justify-center py-6">
      <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
    </div>
    <div v-else-if="results.length === 0" class="py-6 text-center text-xs text-muted-foreground">
      没有找到文档
    </div>
    <div v-else class="max-h-72 overflow-y-auto space-y-1">
      <button
        v-for="c in results"
        :key="c.id"
        class="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted transition-colors"
        @click="emit('pick', c)"
      >
        <Blocks class="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span class="truncate">{{ c.title }}</span>
      </button>
    </div>
  </div>
</template>
