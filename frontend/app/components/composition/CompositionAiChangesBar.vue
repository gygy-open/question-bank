<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Check, ChevronDown, ChevronUp, Sparkles, Undo2 } from '@lucide/vue'
import type { DocumentChange } from '@/lib/compositionDiff'

defineProps<{
  summary: string
  changes: DocumentChange[]
}>()

const emit = defineEmits<{ apply: []; discard: [] }>()

const { t } = useI18n()

const expanded = ref(false)

const KIND_LABEL_KEYS: Record<DocumentChange['kind'], string> = {
  added: 'compositionEditor.aiChanges.kind.added',
  removed: 'compositionEditor.aiChanges.kind.removed',
  moved: 'compositionEditor.aiChanges.kind.moved',
  modified: 'compositionEditor.aiChanges.kind.modified',
}
</script>

<template>
  <div
    class="rounded-md border border-violet-400 bg-violet-50 px-4 py-3 text-sm dark:border-violet-700 dark:bg-violet-900/20"
  >
    <div class="flex items-center gap-3">
      <Sparkles class="h-4 w-4 shrink-0 text-violet-600 dark:text-violet-400" />
      <div class="flex min-w-0 flex-1 flex-col">
        <span class="truncate font-medium">{{ t('compositionEditor.aiChanges.title', { count: changes.length }) }}</span>
        <span class="truncate text-xs text-muted-foreground">{{ summary }}</span>
      </div>
      <Button size="sm" variant="ghost" @click="expanded = !expanded">
        <component :is="expanded ? ChevronUp : ChevronDown" class="mr-1 h-4 w-4" />
        {{ expanded ? t('compositionEditor.aiChanges.collapse') : t('compositionEditor.aiChanges.viewChanges') }}
      </Button>
      <Button size="sm" variant="outline" @click="emit('discard')">
        <Undo2 class="mr-2 h-4 w-4" /> {{ t('compositionEditor.aiChanges.discard') }}
      </Button>
      <Button size="sm" @click="emit('apply')">
        <Check class="mr-2 h-4 w-4" /> {{ t('compositionEditor.aiChanges.apply') }}
      </Button>
    </div>

    <ul v-if="expanded" class="mt-3 space-y-1 border-t border-violet-200 pt-3 dark:border-violet-800">
      <li v-for="change in changes" :key="`${change.kind}-${change.nodeId}`" class="flex items-start gap-2">
        <Badge variant="secondary" class="mt-0.5 shrink-0">{{ t(KIND_LABEL_KEYS[change.kind]) }}</Badge>
        <span class="min-w-0 flex-1 text-xs text-muted-foreground">{{ change.label }}</span>
      </li>
    </ul>
  </div>
</template>
