<script setup lang="ts">
definePageMeta({
  layout: false
})

import CompositionTiptapCanvas from '~/components/composition-next/CompositionTiptapCanvas.vue'
import type { EditorDocument } from '@/lib/compositionDocument'

// 单一 tiptap 文档画布（Phase 0 Spike）演示：编辑/拖拽/框选后观察右侧行数据。
const doc = ref<EditorDocument>({
  nodes: [
    {
      id: 'h1', nodeType: 'heading', props: { level: 1 },
      content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '期中测试卷' }] }] },
      questionId: null, questionRevision: null, questionContent: null,
      sourceQuestionNodeId: null, anchorBeforeNodeId: null, children: [],
    },
    {
      id: 'r1', nodeType: 'rich_text', props: null,
      content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '拖动左侧手柄可整块移动；按住 Ctrl/Cmd 拖拽可跨块框选。' }] }] },
      questionId: null, questionRevision: null, questionContent: null,
      sourceQuestionNodeId: null, anchorBeforeNodeId: null, children: [],
    },
    {
      id: 'q1', nodeType: 'question', props: { number: '1' },
      content: null, questionId: 42, questionRevision: 3,
      questionContent: {
        content_schema_version: 2, q_type: 'single_choice',
        content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '示例题干：1 + 1 = ?' }] }] },
        options: null, answer: null, thinking: null, analysis: null, summary: null, difficulty: 3, source: null,
      },
      sourceQuestionNodeId: null, anchorBeforeNodeId: null, children: [],
    },
    {
      id: 'p1', nodeType: 'page_break', props: null, content: null,
      questionId: null, questionRevision: null, questionContent: null,
      sourceQuestionNodeId: null, anchorBeforeNodeId: null, children: [],
    },
  ],
})
</script>

<template>
  <div class="grid grid-cols-2 gap-4 p-6">
    <Card class="p-4">
      <CompositionTiptapCanvas v-model:document="doc" />
    </Card>
    <Card class="p-4">
      <pre class="text-xs whitespace-pre-wrap">{{ doc }}</pre>
    </Card>
  </div>
</template>