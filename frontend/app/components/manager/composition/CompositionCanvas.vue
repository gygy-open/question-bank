<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Plus, Type, Heading, FileQuestion, SeparatorHorizontal, ListChecks,
} from '@lucide/vue'
import BlockItem from './BlockItem.vue'
import QuestionPicker from './QuestionPicker.vue'
import {
  insertBlockAfter, moveBlock, newEditorBlock, removeBlock,
} from '@/lib/compositionCanvas'
import type { EditorBlock } from '@/lib/compositionCanvas'
import type { CompositionBlockType } from '@/types/composition'
import type { Question } from '@/types'

const props = defineProps<{
  blocks: EditorBlock[]
  subjectId: number | null
}>()

const emit = defineEmits<{
  'update:blocks': [blocks: EditorBlock[]]
}>()

const { $api } = useNuxtApp()

const ADD_ITEMS: { type: CompositionBlockType; label: string; icon: unknown }[] = [
  { type: 'rich_text', label: '文本', icon: Type },
  { type: 'heading', label: '标题', icon: Heading },
  { type: 'question', label: '题目', icon: FileQuestion },
  { type: 'page_break', label: '分页', icon: SeparatorHorizontal },
  { type: 'answer_summary', label: '答案汇总', icon: ListChecks },
]

const pickerOpen = ref(false)

function setBlocks(next: EditorBlock[]) {
  emit('update:blocks', next)
}

function addBlock(type: CompositionBlockType) {
  if (type === 'question') {
    pickerOpen.value = true
    return
  }
  setBlocks(insertBlockAfter(props.blocks, props.blocks.length - 1, newEditorBlock(type)))
}

function onQuestionSelected(question: Question) {
  const block = newEditorBlock('question')
  block.questionId = question.id
  block.questionRevision = question.content_revision
  cacheQuestion(question)
  setBlocks(insertBlockAfter(props.blocks, props.blocks.length - 1, block))
}

function onPatch(key: string, patch: Partial<Pick<EditorBlock, 'content' | 'props'>>) {
  setBlocks(
    props.blocks.map((b) =>
      b.key === key
        ? { ...b, ...patch, props: patch.props ? { ...b.props, ...patch.props } : b.props }
        : b,
    ),
  )
}

function onMove(index: number, direction: 'up' | 'down') {
  setBlocks(moveBlock(props.blocks, index, direction))
}

function onRemove(key: string) {
  setBlocks(removeBlock(props.blocks, key))
}

// --- 题目解析与缓存（按 id 批量拉取，避免逐块 N+1） ---
const questionCache = ref<Map<number, Question>>(new Map())
const loadingIds = ref<Set<number>>(new Set())

function cacheQuestion(q: Question) {
  const m = new Map(questionCache.value)
  m.set(q.id, q)
  questionCache.value = m
}

async function ensureQuestions(ids: number[]) {
  const missing = ids.filter(
    (id) => !questionCache.value.has(id) && !loadingIds.value.has(id),
  )
  if (missing.length === 0) return
  const pending = new Set(loadingIds.value)
  missing.forEach((id) => pending.add(id))
  loadingIds.value = pending
  try {
    const page = await $api<{ items: Question[] }>('/questions', {
      query: { ids: missing, size: missing.length, page: 1 },
    })
    const m = new Map(questionCache.value)
    for (const q of page.items) m.set(q.id, q)
    questionCache.value = m
  } catch {
    // 拉取失败时保持缺失态，BlockItem 展示“题目不可用”。
  } finally {
    const done = new Set(loadingIds.value)
    missing.forEach((id) => done.delete(id))
    loadingIds.value = done
  }
}

watch(
  () => props.blocks,
  (list) => {
    const ids = list
      .filter((b) => b.blockType === 'question' && b.questionId != null)
      .map((b) => b.questionId as number)
    if (ids.length) ensureQuestions(ids)
  },
  { immediate: true, deep: true },
)

function questionFor(block: EditorBlock): Question | null {
  return block.questionId != null ? questionCache.value.get(block.questionId) ?? null : null
}

function isLoading(block: EditorBlock): boolean {
  return block.questionId != null && loadingIds.value.has(block.questionId)
}

function isStale(block: EditorBlock): boolean {
  if (block.questionId == null || block.questionRevision == null) return false
  const q = questionCache.value.get(block.questionId)
  return !!q && q.content_revision > block.questionRevision
}

const hasStale = computed(() => props.blocks.some(isStale))
defineExpose({ hasStale })
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-if="blocks.length === 0" class="rounded-lg border border-dashed py-16 text-center">
      <p class="mb-4 text-sm text-muted-foreground">画布还是空的，添加第一个块开始编辑。</p>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline">
            <Plus class="mr-2 h-4 w-4" /> 添加块
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center">
          <DropdownMenuItem v-for="item in ADD_ITEMS" :key="item.type" @click="addBlock(item.type)">
            <component :is="item.icon" class="mr-2 h-4 w-4" /> {{ item.label }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <template v-else>
      <BlockItem
        v-for="(block, index) in blocks"
        :key="block.key"
        :block="block"
        :index="index"
        :total="blocks.length"
        :question="questionFor(block)"
        :question-loading="isLoading(block)"
        :stale="isStale(block)"
        @patch="onPatch(block.key, $event)"
        @move="onMove(index, $event)"
        @remove="onRemove(block.key)"
      />

      <div class="flex justify-center pt-1">
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <Plus class="mr-2 h-4 w-4" /> 添加块
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="center">
            <DropdownMenuItem v-for="item in ADD_ITEMS" :key="item.type" @click="addBlock(item.type)">
              <component :is="item.icon" class="mr-2 h-4 w-4" /> {{ item.label }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </template>

    <QuestionPicker
      v-model:open="pickerOpen"
      :subject-id="subjectId"
      @select="onQuestionSelected"
    />
  </div>
</template>
