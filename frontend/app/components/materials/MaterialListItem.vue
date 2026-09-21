<script setup lang="ts">
import { ArchiveRestore, FilePenLine, Layers3, Lock, Trash2 } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import RichContent from '@/components/rich-editor/RichContent.vue'
import type { StimulusListItem } from '@/types'

const props = defineProps<{
  material: StimulusListItem
  canEdit: boolean
}>()

defineEmits<{
  delete: [material: StimulusListItem]
  restore: [material: StimulusListItem]
}>()

const isDeleted = computed(() => props.material.deleted_at !== null)

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
      <div v-if="canEdit" class="flex shrink-0 items-center gap-1">
        <Button v-if="isDeleted" variant="ghost" size="icon" title="恢复题目材料" aria-label="恢复题目材料" @click="$emit('restore', material)">
          <ArchiveRestore class="size-4" />
        </Button>
        <template v-else>
          <Button as-child variant="ghost" size="icon" title="编辑题目材料" aria-label="编辑题目材料">
            <NuxtLink :to="`/materials/${material.id}/edit`"><FilePenLine class="size-4" /></NuxtLink>
          </Button>
          <Button variant="ghost" size="icon" class="text-destructive" title="删除题目材料" aria-label="删除题目材料" @click="$emit('delete', material)">
            <Trash2 class="size-4" />
          </Button>
        </template>
      </div>
    </div>
  </article>
</template>