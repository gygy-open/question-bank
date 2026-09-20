<script setup lang="ts">
import { FilePenLine, Layers3, Lock } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import RichContent from '@/components/rich-editor/RichContent.vue'
import type { StimulusListItem } from '@/types'

defineProps<{
  material: StimulusListItem
  canEdit: boolean
}>()

const statusLabel: Record<string, string> = {
  draft: '草稿',
  pending: '待审核',
  published: '已发布',
  archived: '已归档',
}
</script>

<template>
  <article class="border-b px-1 py-4 last:border-b-0">
    <div class="flex items-start gap-4">
      <div class="min-w-0 flex-1 space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-mono text-xs text-muted-foreground">#{{ material.id }}</span>
          <Badge variant="secondary">{{ statusLabel[material.status] || material.status }}</Badge>
          <Badge v-if="material.visibility === 'private'" variant="outline" class="gap-1">
            <Lock class="size-3" /> 私有
          </Badge>
          <span v-if="material.source" class="truncate text-xs text-muted-foreground">{{ material.source }}</span>
        </div>
        <RichContent :content="material.content" empty-text="（空题目材料）" class="line-clamp-4 text-sm" />
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Layers3 class="size-3.5" />
          {{ material.question_group_count }} 个题组使用
        </div>
      </div>
      <Button v-if="canEdit" as-child variant="ghost" size="icon" title="编辑题目材料" aria-label="编辑题目材料">
        <NuxtLink :to="`/materials/${material.id}/edit`">
          <FilePenLine class="size-4" />
        </NuxtLink>
      </Button>
    </div>
  </article>
</template>