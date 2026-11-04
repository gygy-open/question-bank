<script setup lang="ts">
/**
 * 元素类型树的一个节点(递归渲染子节点)。
 *
 * 只负责展示与发出操作事件;增删改、移动、合并由页面统一处理(弹窗、确认、刷新)。
 */
import { ref } from 'vue'
import { ChevronDown, ChevronRight, MoreHorizontal } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { domainClasses, type StructTypeNode } from '@/lib/structure'
import type { StructType } from '~/types'

const props = defineProps<{
  node: StructTypeNode
  /** 学科全部类型(配色需要按根节点判断领域)。 */
  types: StructType[]
  /** 是否可编辑;为 false 时不显示操作菜单。 */
  editable: boolean
  /** 搜索中:强制展开,让命中的节点可见。 */
  forceOpen?: boolean
}>()

const emit = defineEmits<{
  (e: 'add-child', node: StructTypeNode): void
  (e: 'edit', node: StructTypeNode): void
  (e: 'move', node: StructTypeNode): void
  (e: 'merge', node: StructTypeNode): void
  (e: 'toggle-status', node: StructTypeNode): void
  (e: 'delete', node: StructTypeNode): void
}>()

const { t } = useI18n()

// 第一层(领域)默认展开,更深的层级默认折叠,避免类型多时页面过长。
const open = ref(props.node.depth === 0)

// 状态徽标配色:待确认醒目、停用弱化。
const STATUS_CLASS: Record<string, string> = {
  candidate: 'border-amber-500/50 text-amber-700 dark:text-amber-300',
  active: 'hidden',
  deprecated: 'text-muted-foreground line-through',
}
</script>

<template>
  <div>
    <div
      :class="cn('group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent/50', node.status === 'deprecated' && 'opacity-60')"
      :style="{ paddingLeft: `${node.depth * 18 + 8}px` }"
    >
      <button
        type="button"
        class="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"
        :class="node.children.length ? '' : 'invisible'"
        @click="open = !open"
      >
        <ChevronDown v-if="open || forceOpen" class="h-4 w-4" />
        <ChevronRight v-else class="h-4 w-4" />
      </button>
      <span :class="cn('h-2 w-2 shrink-0 rounded-full', domainClasses(types, node.id).dot)" />
      <span class="font-medium">{{ node.name }}</span>
      <code class="text-xs text-muted-foreground">{{ node.code }}</code>
      <Badge variant="outline" :class="cn('h-5 px-1.5 text-[11px] font-normal', STATUS_CLASS[node.status])">
        {{ t(`structure.typeStatuses.${node.status}`) }}
      </Badge>
      <span v-if="node.definition" class="min-w-0 flex-1 truncate text-xs text-muted-foreground" :title="node.definition">
        {{ node.definition }}
      </span>
      <span v-else class="flex-1" />
      <span class="shrink-0 text-xs text-muted-foreground" :title="t('structure.types.usageHint')">
        {{ t('structure.types.usage', { count: node.usage }) }}
      </span>

      <DropdownMenu v-if="editable">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" size="icon" class="h-7 w-7 opacity-60 group-hover:opacity-100" :title="t('common.moreActions')">
            <MoreHorizontal class="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem @click="emit('add-child', node)">{{ t('structure.types.addChild') }}</DropdownMenuItem>
          <DropdownMenuItem @click="emit('edit', node)">{{ t('common.edit') }}</DropdownMenuItem>
          <DropdownMenuItem v-if="node.parent_id != null" @click="emit('move', node)">{{ t('structure.types.move') }}</DropdownMenuItem>
          <DropdownMenuItem v-if="node.parent_id != null" @click="emit('merge', node)">{{ t('structure.types.merge') }}</DropdownMenuItem>
          <DropdownMenuItem @click="emit('toggle-status', node)">
            {{ node.status === 'active' ? t('structure.types.deactivate') : t('structure.types.activate') }}
          </DropdownMenuItem>
          <DropdownMenuSeparator v-if="node.parent_id != null" />
          <DropdownMenuItem v-if="node.parent_id != null" variant="destructive" @click="emit('delete', node)">
            {{ t('common.delete') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <template v-if="open || forceOpen">
      <StructTypeTreeItem
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :types="types"
        :editable="editable"
        :force-open="forceOpen"
        @add-child="emit('add-child', $event)"
        @edit="emit('edit', $event)"
        @move="emit('move', $event)"
        @merge="emit('merge', $event)"
        @toggle-status="emit('toggle-status', $event)"
        @delete="emit('delete', $event)"
      />
    </template>
  </div>
</template>
