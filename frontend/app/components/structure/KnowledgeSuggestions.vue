<script setup lang="ts">
/**
 * 「推荐知识点」(规格 §12.3 N8):按题干条目 / 解答方法的类型 → 知识点映射,列出题目尚未标注的知识点,
 * 一键追加到题目上。类型的知识点映射在「元素类型」页维护;没有推荐时不显示。
 */
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { BookOpen, Plus } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { getApiErrorDetail } from '@/lib/apiErrors'

const props = defineProps<{ questionId: number, editable: boolean }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const { t } = useI18n()
const api = useStructure()
const { $api } = useNuxtApp()

const items = ref<Array<{ id: number, name: string, matches: number }>>([])
const currentIds = ref<number[]>([])
const busyId = ref<number | null>(null)

async function load(): Promise<void> {
  try {
    const result = await api.knowledgeSuggestions(props.questionId)
    items.value = result.items
    currentIds.value = result.current_ids
  } catch {
    items.value = []
  }
}

async function add(id: number): Promise<void> {
  busyId.value = id
  try {
    await $api(`/questions/${props.questionId}`, {
      method: 'PUT',
      body: { knowledge_point_ids: [...currentIds.value, id] },
    })
    toast.success(t('structure.knowledge.added'))
    emit('changed')
    await load()
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busyId.value = null
  }
}

watch(() => props.questionId, () => { void load() }, { immediate: true })
defineExpose({ load })
</script>

<template>
  <section v-if="items.length" class="space-y-1.5 rounded-md border border-dashed px-3 py-2">
    <h4 class="text-xs font-medium text-muted-foreground">{{ t('structure.knowledge.title') }}</h4>
    <div class="flex flex-wrap gap-1.5">
      <span v-for="item in items" :key="item.id" class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs">
        <BookOpen class="h-3 w-3 text-muted-foreground" />{{ item.name }}
        <Button
          v-if="editable"
          size="icon"
          variant="ghost"
          class="h-5 w-5"
          :disabled="busyId === item.id"
          :title="t('structure.knowledge.add')"
          @click="add(item.id)"
        ><Plus class="h-3 w-3" /></Button>
      </span>
    </div>
  </section>
</template>
