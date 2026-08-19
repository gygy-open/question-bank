<script setup lang="ts">
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { Eye } from '@lucide/vue'
import QuestionDisplayOverride from './QuestionDisplayOverride.vue'
import type { EditorBlock } from '../blockRegistry'

const props = defineProps<{ block: EditorBlock }>()
const emit = defineEmits<{ change: []; 'view-detail': [] }>()
</script>

<template>
  <DropdownMenuItem @click="emit('view-detail')">
    <Eye /> 查看题目
  </DropdownMenuItem>
  <QuestionDisplayOverride :block="props.block" @change="emit('change')" />
  <DropdownMenuSeparator />
</template>
