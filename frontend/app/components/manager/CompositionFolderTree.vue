<script setup lang="ts">
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  ChevronRight,
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  FolderInput,
  Trash2,
} from '@lucide/vue'
import type { CompositionFolderNode } from '~/types/composition'

defineProps<{
  nodes: CompositionFolderNode[]
  selectedId: number | null
  expanded: Set<number>
  depth?: number
}>()

const emit = defineEmits<{
  select: [id: number]
  toggle: [id: number]
  'create-child': [parentId: number]
  rename: [folder: CompositionFolderNode]
  move: [folder: CompositionFolderNode]
  delete: [folder: CompositionFolderNode]
}>()
</script>

<template>
  <ul class="space-y-0.5">
    <li v-for="node in nodes" :key="node.id">
      <div
        class="group/row flex items-center gap-1 rounded px-1.5 py-1 text-sm hover:bg-accent"
        :class="selectedId === node.id ? 'bg-accent font-medium text-accent-foreground' : ''"
        :style="{ paddingLeft: `${(depth ?? 0) * 12 + 6}px` }"
      >
        <button
          type="button"
          class="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"
          :class="node.children.length ? '' : 'invisible'"
          @click.stop="emit('toggle', node.id)"
        >
          <ChevronRight
            class="h-3.5 w-3.5 transition-transform"
            :class="expanded.has(node.id) ? 'rotate-90' : ''"
          />
        </button>
        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-1.5 text-left"
          @click="emit('select', node.id)"
        >
          <component
            :is="expanded.has(node.id) && node.children.length ? FolderOpen : Folder"
            class="h-4 w-4 shrink-0 text-muted-foreground"
          />
          <span class="truncate">{{ node.name }}</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="h-6 w-6 shrink-0 opacity-0 group-hover/row:opacity-100 data-[state=open]:opacity-100"
              @click.stop
            >
              <MoreHorizontal class="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem @click="emit('create-child', node.id)">
              <FolderPlus class="mr-2 h-4 w-4" /> 新建子文件夹
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('rename', node)">
              <Pencil class="mr-2 h-4 w-4" /> 重命名
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('move', node)">
              <FolderInput class="mr-2 h-4 w-4" /> 移动
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="text-destructive" @click="emit('delete', node)">
              <Trash2 class="mr-2 h-4 w-4" /> 删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CompositionFolderTree
        v-if="node.children.length && expanded.has(node.id)"
        :nodes="node.children"
        :selected-id="selectedId"
        :expanded="expanded"
        :depth="(depth ?? 0) + 1"
        @select="emit('select', $event)"
        @toggle="emit('toggle', $event)"
        @create-child="emit('create-child', $event)"
        @rename="emit('rename', $event)"
        @move="emit('move', $event)"
        @delete="emit('delete', $event)"
      />
    </li>
  </ul>
</template>
