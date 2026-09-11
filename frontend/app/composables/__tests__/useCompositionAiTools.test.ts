// 桥接层的行为契约：作用域注册、权限门禁、pending 互斥、失败可读。
//
// 两个 handler 通过 registerClientTool 进入模块级注册表，再由 useAiClientTools().run 分发
// —— 与真实 SSE 链路同一条路径，所以这里连着一起测。
//
// 用真的 <KeepAlive> 挂载：app.vue 是全局 <NuxtPage keepalive />，「导航走之后组件还活着」
// 正是工具必须靠 onDeactivated 注销的原因，用 mount/unmount 测不出这条。
import { describe, it, expect, vi } from 'vitest'
import { createApp, defineComponent, h, KeepAlive, nextTick, ref } from 'vue'

vi.stubGlobal('navigateTo', vi.fn())
vi.stubGlobal('useCookie', () => ({ value: 'token' }))
vi.stubGlobal('useNuxtApp', () => ({ runWithContext: (fn: () => unknown) => fn() }))

const { useAiClientTools } = await import('../useAiClientTools')
const { useCompositionAiTools } = await import('../useCompositionAiTools')
const {
  createHeadingNode,
  createQuestionDetailsModule,
  createQuestionNode,
  headingTextToDoc,
  normalizeDocument,
} = await import('@/lib/compositionDocument')

import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import type { DocumentChange } from '@/lib/compositionDiff'
import type { Question } from '@/types'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function fakeQuestion(id: number): Question {
  return {
    id,
    content_revision: 1,
    content_schema_version: 2,
    content: richDoc(`题干${id}`),
    options: null,
    answer: null,
    thinking: null,
    analysis: null,
    summary: null,
    q_type: 'free_response',
    status: 'approved',
    difficulty: 3,
    source: 'seed',
  } as unknown as Question
}

function docOf(...nodes: EditorNode[]): EditorDocument {
  return normalizeDocument({ nodes })
}

function headingNode(text: string): EditorNode {
  const node = createHeadingNode(2)
  node.content = headingTextToDoc(text)
  return node
}

function mountEditor(initial: EditorDocument, canEdit = true) {
  const doc = ref<EditorDocument>(initial)
  const pending = ref<{ changes: DocumentChange[]; summary: string } | null>(null)
  const onScreen = ref(true)

  const Page = defineComponent({
    setup() {
      useCompositionAiTools({
        getDocument: () => doc.value,
        getTitle: () => '期中测验',
        getQuestionDisplay: () => ({ answer: true, thinking: false, analysis: false, summary: false }),
        getNumberingEnabled: () => true,
        getScoringEnabled: () => false,
        canEdit: () => canEdit,
        hasPending: () => pending.value != null,
        stagePending: (next, changes, summary) => {
          doc.value = next
          pending.value = { changes, summary }
        },
        loadQuestions: async (ids) => ids.map(fakeQuestion),
      })
      return () => h('div')
    },
  })

  const Host = defineComponent({
    setup: () => () => h(KeepAlive, null, {
      default: () => (onScreen.value ? h(Page) : h('span')),
    }),
  })

  const app = createApp(Host)
  app.mount(document.createElement('div'))
  return { doc, pending, onScreen, unmount: () => app.unmount() }
}

const run = (name: string, args: Record<string, any> = {}) => useAiClientTools().run(name, args)

describe('useCompositionAiTools', () => {
  it('未注册时干净失败，而不是让 run 挂起', async () => {
    const res = await run('read_composition_outline')
    expect(res.ok).toBe(false)
    expect(res.content).toContain('read_composition_outline')
  })

  it('导航离开（keepalive 下只是 deactivate）后工具就失效', async () => {
    const editor = mountEditor(docOf(headingNode('一、选择题')))
    await nextTick()
    expect((await run('read_composition_outline')).ok).toBe(true)

    // 组件仍然 mounted，只是被缓存起来 —— 不能再让助手改这块看不见的画布。
    editor.onScreen.value = false
    await nextTick()
    expect((await run('read_composition_outline')).ok).toBe(false)

    editor.onScreen.value = true
    await nextTick()
    expect((await run('read_composition_outline')).ok).toBe(true)

    editor.unmount()
    await nextTick()
    expect((await run('read_composition_outline')).ok).toBe(false)
  })

  it('大纲带节点 id、稿件级显隐默认值，并保留模块嵌套', async () => {
    const q = createQuestionNode(fakeQuestion(7))
    const mod = createQuestionDetailsModule('all')
    const editor = mountEditor(docOf(q, mod))
    await nextTick()

    const res = await run('read_composition_outline')
    expect(res.content).toContain('默认展示答案')
    expect(res.content).toContain(`[${q.id}] question #7`)
    // 派生的 answer_item 缩进在模块下面；拍平会让「插到第一题后面」分不清落点。
    expect(res.content).toContain('    └ [')
    expect(res.content).toContain(`answer_item ← ${q.id}`)
    // 题干只给摘要，不把几千 token 的冻结快照喂给模型。
    expect(res.content).not.toContain('content_schema_version')

    editor.unmount()
  })

  it('edit 只挂待确认预览，明说尚未保存', async () => {
    const h1 = headingNode('一、选择题')
    const editor = mountEditor(docOf(h1))
    await nextTick()

    const res = await run('edit_composition', {
      summary: '补一道题',
      operations: [{ op: 'insert_nodes', after: h1.id, nodes: [{ type: 'question', question_id: 3 }] }],
    })

    expect(res.ok).toBe(true)
    expect(res.content).toContain('等待用户点「应用」')
    expect(editor.pending.value!.summary).toBe('补一道题')
    expect(editor.pending.value!.changes).toHaveLength(1)
    expect(editor.doc.value.nodes).toHaveLength(2)

    editor.unmount()
  })

  it('上一批还没确认时拒绝再叠一批', async () => {
    const editor = mountEditor(docOf(headingNode('A')))
    await nextTick()
    editor.pending.value = { changes: [], summary: 'x' }

    const res = await run('edit_composition', {
      operations: [{ op: 'insert_nodes', after: 'end', nodes: [{ type: 'page_break' }] }],
    })
    expect(res.ok).toBe(false)
    expect(res.content).toContain('确认')

    editor.unmount()
  })

  it('没有编辑权限时只读得到大纲', async () => {
    const editor = mountEditor(docOf(headingNode('A')), false)
    await nextTick()

    expect((await run('read_composition_outline')).ok).toBe(true)
    const res = await run('edit_composition', {
      operations: [{ op: 'insert_nodes', after: 'end', nodes: [{ type: 'page_break' }] }],
    })
    expect(res.ok).toBe(false)
    expect(res.content).toContain('权限')
    expect(editor.pending.value).toBeNull()

    editor.unmount()
  })

  it('一条都没成功时不挂预览，把原因原样回给模型', async () => {
    const editor = mountEditor(docOf(headingNode('A')))
    await nextTick()

    const res = await run('edit_composition', {
      operations: [{ op: 'remove_nodes', node_ids: ['ghost'] }],
    })
    expect(res.ok).toBe(false)
    expect(res.content).toContain('ghost')
    expect(editor.pending.value).toBeNull()

    editor.unmount()
  })

  it('部分失败时其余仍生效，并逐条回报', async () => {
    const editor = mountEditor(docOf(headingNode('A')))
    await nextTick()

    const res = await run('edit_composition', {
      operations: [
        { op: 'insert_nodes', after: 'end', nodes: [{ type: 'page_break' }] },
        { op: 'remove_nodes', node_ids: ['ghost'] },
      ],
    })
    expect(res.ok).toBe(true)
    expect(res.content).toContain('以下操作失败')
    expect(res.content).toContain('ghost')
    expect(editor.doc.value.nodes).toHaveLength(2)

    editor.unmount()
  })
})
