<script setup lang="ts">
/**
 * 组卷侧栏的「结构分布」:当前组卷中题目的元素类型分布(只统计已采纳的拆解)。
 *
 * 用来回答「这张卷子代数 / 几何 / 统计各占多少、常见的条件与设问类型有哪些」。
 * 题目变化频繁(拖动、增删),因此去抖后再请求。
 */
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Shapes } from '@lucide/vue'
import { domainClasses } from '@/lib/structure'
import { cn } from '@/lib/utils'
import type { StructDistribution, StructType } from '~/types'

const props = defineProps<{
  /** 组卷中的题目 id(可重复,统计时去重)。 */
  questionIds: number[]
  subjectId: number | null
}>()

const { t } = useI18n()
const api = useStructure()

// region 状态

const distribution = ref<StructDistribution | null>(null)
const types = ref<StructType[]>([])
const loading = ref(false)

// 具体类型最多展示几条。
const TOP_TYPES = 6

// endregion

// region 计算属性

const uniqueIds = computed(() => [...new Set(props.questionIds)])

/** 领域条:按题数占比(以已结构化题数为分母)。 */
const domains = computed(() => {
  const d = distribution.value
  if (!d || !d.structured) return []
  return d.domains.map(item => ({
    ...item,
    percent: Math.round((item.count / d.structured) * 100),
    classes: domainClasses(types.value, item.type_id),
  }))
})

/** 具体类型(排除领域根节点本身,它已经在领域条里体现)。 */
const topTypes = computed(() =>
  (distribution.value?.types ?? []).filter(item => item.path.length > 1).slice(0, TOP_TYPES))

// endregion

// region 内部辅助函数

const refresh = useDebounceFn(async () => {
  if (!uniqueIds.value.length) {
    distribution.value = { questions: 0, structured: 0, domains: [], types: [] }
    return
  }
  loading.value = true
  try {
    distribution.value = await api.distribution(uniqueIds.value)
  } catch {
    // 统计失败不影响组卷,静默保留上一次结果。
  } finally {
    loading.value = false
  }
}, 800)

async function loadTypes(): Promise<void> {
  if (props.subjectId == null) return
  try {
    types.value = (await api.listTypes(props.subjectId)).items
  } catch {
    types.value = []
  }
}

// endregion

watch(uniqueIds, (next, previous) => {
  // 只有题目集合真的变了才重新统计(节点内容编辑不会触发请求)。
  if (previous && next.length === previous.length && next.every((id, i) => id === previous[i])) return
  void refresh()
}, { immediate: true })
watch(() => props.subjectId, () => { void loadTypes() }, { immediate: true })
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center gap-2 text-sm font-medium">
      <Shapes class="h-4 w-4" /> {{ t('structure.composition.title') }}
    </div>
    <p class="text-xs text-muted-foreground">
      {{ t('structure.composition.coverage', { structured: distribution?.structured ?? 0, total: uniqueIds.length }) }}
    </p>
    <div v-if="domains.length" class="space-y-1.5">
      <div v-for="item in domains" :key="item.type_id" class="space-y-0.5">
        <div class="flex justify-between text-xs">
          <span :class="item.classes.text">{{ item.name }}</span>
          <span class="text-muted-foreground">{{ t('structure.composition.count', { count: item.count }) }}</span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-muted">
          <div :class="cn('h-full rounded-full', item.classes.dot)" :style="{ width: `${item.percent}%` }" />
        </div>
      </div>
    </div>
    <ul v-if="topTypes.length" class="space-y-1 text-xs">
      <li v-for="item in topTypes" :key="item.type_id" class="flex justify-between gap-2">
        <span class="truncate" :title="item.path.join(' › ')">{{ item.path.slice(1).join(' › ') }}</span>
        <span class="shrink-0 text-muted-foreground">{{ item.count }}</span>
      </li>
    </ul>
    <p v-if="!loading && distribution && !distribution.structured && uniqueIds.length" class="text-xs text-muted-foreground">
      {{ t('structure.composition.none') }}
    </p>
  </div>
</template>
