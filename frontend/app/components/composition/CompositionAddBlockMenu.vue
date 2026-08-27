<script setup lang="ts">
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Plus, Type, Heading, FileQuestion, SeparatorHorizontal, ListChecks, FileStack } from '@lucide/vue'

export type AddBlockKind = 'rich_text' | 'heading' | 'question' | 'page_break' | 'module_summary' | 'insert_composition'

withDefaults(defineProps<{ align?: 'start' | 'center' | 'end' }>(), { align: 'center' })

const emit = defineEmits<{ add: [kind: AddBlockKind] }>()
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <slot>
        <Button variant="outline" size="sm">
          <Plus class="mr-2 h-4 w-4" /> 添加节点
        </Button>
      </slot>
    </DropdownMenuTrigger>
    <DropdownMenuContent :align="align">
      <DropdownMenuItem @click="emit('add', 'rich_text')"><Type class="mr-2 h-4 w-4" /> 文本</DropdownMenuItem>
      <DropdownMenuItem @click="emit('add', 'heading')"><Heading class="mr-2 h-4 w-4" /> 标题</DropdownMenuItem>
      <DropdownMenuItem @click="emit('add', 'question')"><FileQuestion class="mr-2 h-4 w-4" /> 题目</DropdownMenuItem>
      <DropdownMenuItem @click="emit('add', 'page_break')"><SeparatorHorizontal class="mr-2 h-4 w-4" /> 分页</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel class="text-xs">模块</DropdownMenuLabel>
      <DropdownMenuItem @click="emit('add', 'module_summary')"><ListChecks class="mr-2 h-4 w-4" /> 参考答案模块</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @click="emit('add', 'insert_composition')"><FileStack class="mr-2 h-4 w-4" /> 插入稿件</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
