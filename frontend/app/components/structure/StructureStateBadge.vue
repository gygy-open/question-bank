<script setup lang="ts">
/**
 * 题干结构化状态徽标:未拆解 / 待审 / 已采纳 / 已过期。
 * 题库列表、审核页共用;未拆解默认不显示(避免列表满屏灰标),需要时传 showNone。
 */
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import type { StructState } from '~/types'

const props = defineProps<{
  state: StructState | null | undefined
  /** 是否也显示「未拆解」。 */
  showNone?: boolean
}>()

const { t } = useI18n()

// 各状态的配色:待审醒目(需要人处理)、过期警示、已采纳低调。
const CLASSES: Record<StructState, string> = {
  none: 'text-muted-foreground',
  draft: 'border-amber-500/50 text-amber-700 dark:text-amber-300 bg-amber-500/10',
  accepted: 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10',
  stale: 'border-destructive/40 text-destructive bg-destructive/10',
}

const visible = computed(() => !!props.state && (props.state !== 'none' || props.showNone))
</script>

<template>
  <Badge v-if="visible && state" variant="outline" :class="CLASSES[state]" class="font-normal">
    {{ t(`structure.states.${state}`) }}
  </Badge>
</template>
