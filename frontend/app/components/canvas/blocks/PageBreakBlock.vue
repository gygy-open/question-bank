<script setup lang="ts">
import { SeparatorHorizontal } from '@lucide/vue'
import type { EditorBlock } from '../blockRegistry'

defineProps<{
  block: EditorBlock
}>()
</script>

<template>
  <div class="pl-8 pr-4 py-1">
    <div
      class="flex items-center gap-2 text-xs text-muted-foreground border-t border-dashed border-muted-foreground/40 pt-2"
    >
      <SeparatorHorizontal class="h-3.5 w-3.5" />
      <span>分页符</span>
    </div>
  </div>
</template>
