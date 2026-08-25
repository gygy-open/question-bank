import { describe, it, expect } from 'vitest'
import {
  blockToReplaceItem,
  blocksToReplaceRequest,
  collectBlockIssues,
  editorBlocksFromDetail,
  generateBlockKey,
  headingDocToText,
  headingHasRichInline,
  headingTextToDoc,
  insertBlockAfter,
  moveBlock,
  newEditorBlock,
  reconcileAfterSave,
  removeBlock,
  snapshotBlocks,
} from '@/lib/compositionCanvas'
import type { EditorBlock } from '@/lib/compositionCanvas'
import type { CompositionBlock, CompositionBlocksReplaceResponse } from '@/types/composition'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

describe('temp id / key 生成', () => {
  it('generateBlockKey 唯一', () => {
    const keys = new Set(Array.from({ length: 200 }, () => generateBlockKey()))
    expect(keys.size).toBe(200)
  })

  it('newEditorBlock 各类型默认值', () => {
    expect(newEditorBlock('rich_text').content).toEqual({ type: 'doc', content: [{ type: 'paragraph' }] })
    expect(newEditorBlock('heading').props).toEqual({ level: 2 })
    expect(newEditorBlock('answer_summary').props).toEqual({ mode: 'all' })
    expect(newEditorBlock('page_break').content).toBeNull()
    const q = newEditorBlock('question')
    expect(q.content).toBeNull()
    expect(q.questionId).toBeNull()
  })
})

describe('blockToReplaceItem 载荷', () => {
  it('新建块用 temp_id=key，已有块用 id', () => {
    const fresh = newEditorBlock('rich_text')
    fresh.content = richDoc('hello')
    const item = blockToReplaceItem(fresh)
    expect(item.temp_id).toBe(fresh.key)
    expect(item.id).toBeUndefined()
    expect(item.content).toEqual(richDoc('hello'))

    const existing: EditorBlock = { ...fresh, serverId: 42 }
    const item2 = blockToReplaceItem(existing)
    expect(item2.id).toBe(42)
    expect(item2.temp_id).toBeUndefined()
  })

  it('heading 带 level，question 带 question_id，page_break 无内容', () => {
    const h = newEditorBlock('heading')
    h.content = richDoc('标题')
    expect(blockToReplaceItem(h).props).toEqual({ level: 2 })

    const q = newEditorBlock('question')
    q.questionId = 5
    q.questionRevision = 3
    const qi = blockToReplaceItem(q)
    expect(qi.question_id).toBe(5)
    expect(qi.question_revision).toBe(3)

    const pb = newEditorBlock('page_break')
    const pbi = blockToReplaceItem(pb)
    expect(pbi.content).toBeUndefined()
    expect(pbi.props).toBeUndefined()
  })

  it('blocksToReplaceRequest 组装 expected_revision 与可选 batch_id', () => {
    const b = newEditorBlock('page_break')
    const req = blocksToReplaceRequest([b], 7, 'batch-1')
    expect(req.expected_revision).toBe(7)
    expect(req.batch_id).toBe('batch-1')
    expect(req.blocks).toHaveLength(1)
    expect(blocksToReplaceRequest([b], 7).batch_id).toBeUndefined()
  })
})

describe('线性重排', () => {
  const mk = (n: number) => Array.from({ length: n }, (_, i) => ({ ...newEditorBlock('page_break'), key: `k${i}` }))

  it('moveBlock 上/下移交换相邻', () => {
    const list = mk(3)
    const up = moveBlock(list, 1, 'up')
    expect(up.map((b) => b.key)).toEqual(['k1', 'k0', 'k2'])
    const down = moveBlock(list, 1, 'down')
    expect(down.map((b) => b.key)).toEqual(['k0', 'k2', 'k1'])
  })

  it('moveBlock 越界返回原序（浅拷贝）', () => {
    const list = mk(2)
    expect(moveBlock(list, 0, 'up').map((b) => b.key)).toEqual(['k0', 'k1'])
    expect(moveBlock(list, 1, 'down').map((b) => b.key)).toEqual(['k0', 'k1'])
  })

  it('removeBlock 按 key 删除', () => {
    const list = mk(3)
    expect(removeBlock(list, 'k1').map((b) => b.key)).toEqual(['k0', 'k2'])
  })

  it('insertBlockAfter 在指定位置后插入', () => {
    const list = mk(2)
    const b = { ...newEditorBlock('page_break'), key: 'kx' }
    expect(insertBlockAfter(list, 0, b).map((x) => x.key)).toEqual(['k0', 'kx', 'k1'])
    expect(insertBlockAfter(list, -1, b).map((x) => x.key)).toEqual(['kx', 'k0', 'k1'])
    expect(insertBlockAfter(list, 9, b).map((x) => x.key)).toEqual(['k0', 'k1', 'kx'])
  })
})

describe('heading RichDoc 转换', () => {
  it('纯文本 <-> 单段落 RichDoc 往返', () => {
    const doc = headingTextToDoc('第一章')
    expect(doc).toEqual(richDoc('第一章'))
    expect(headingDocToText(doc)).toBe('第一章')
    expect(headingDocToText(headingTextToDoc(''))).toBe('')
  })

  it('空文本产出单个空段落（后端可接受）', () => {
    expect(headingTextToDoc('')).toEqual({ type: 'doc', content: [{ type: 'paragraph' }] })
  })

  it('headingHasRichInline 检测公式等非文本行内节点', () => {
    const withMath = {
      type: 'doc' as const,
      content: [{ type: 'paragraph', content: [{ type: 'inlineMath', attrs: { latex: 'x^2' } }] }],
    }
    expect(headingHasRichInline(withMath)).toBe(true)
    expect(headingHasRichInline(richDoc('纯文本'))).toBe(false)
    // 纯文本抽取不会破坏原公式 doc（转换只在用户显式确认时发生）。
    expect(headingDocToText(withMath)).toBe('')
  })
})

describe('脏检测快照与保存问题', () => {
  it('snapshotBlocks 忽略 key/serverId/questionRevision', () => {
    const a = newEditorBlock('rich_text')
    a.content = richDoc('x')
    const b: EditorBlock = { ...a, key: 'other', serverId: 99 }
    expect(snapshotBlocks([a])).toBe(snapshotBlocks([b]))

    const q1 = newEditorBlock('question')
    q1.questionId = 1
    q1.questionRevision = 2
    const q2: EditorBlock = { ...q1, questionRevision: 9 }
    expect(snapshotBlocks([q1])).toBe(snapshotBlocks([q2]))
  })

  it('内容变化会改变快照', () => {
    const a = newEditorBlock('rich_text')
    a.content = richDoc('x')
    const b: EditorBlock = { ...a, content: richDoc('y') }
    expect(snapshotBlocks([a])).not.toBe(snapshotBlocks([b]))
  })

  it('collectBlockIssues 标记空文本/空标题/缺题', () => {
    const empty = newEditorBlock('rich_text')
    const emptyHeading = newEditorBlock('heading')
    const q = newEditorBlock('question')
    const issues = collectBlockIssues([empty, emptyHeading, q])
    expect(issues).toHaveLength(3)
    const ok = newEditorBlock('rich_text')
    ok.content = richDoc('内容')
    expect(collectBlockIssues([ok])).toHaveLength(0)
  })
})

describe('保存后重建保留 key', () => {
  it('editorBlocksFromDetail 映射服务端字段', () => {
    const detail: CompositionBlock[] = [
      { id: 1, composition_id: 9, sequence: 0, schema_version: 1, block_type: 'heading', content: richDoc('标题'), props: { level: 3 }, question_id: null, question_revision: null },
      { id: 2, composition_id: 9, sequence: 1, schema_version: 1, block_type: 'question', content: null, props: null, question_id: 5, question_revision: 7 },
    ]
    const blocks = editorBlocksFromDetail(detail)
    expect(blocks[0]!.serverId).toBe(1)
    expect(blocks[0]!.props).toEqual({ level: 3 })
    expect(blocks[1]!.questionId).toBe(5)
    expect(blocks[1]!.questionRevision).toBe(7)
  })

  it('reconcileAfterSave 复用已有 key 与 temp key', () => {
    const existing: EditorBlock = { ...newEditorBlock('rich_text'), key: 'existing-key', serverId: 10, content: richDoc('a') }
    const fresh: EditorBlock = { ...newEditorBlock('page_break'), key: 'temp-key' }
    const prev = [existing, fresh]

    const resp: CompositionBlocksReplaceResponse = {
      revision: 3,
      id_map: { 'temp-key': 20 },
      blocks: [
        { id: 10, composition_id: 9, sequence: 0, schema_version: 1, block_type: 'rich_text', content: richDoc('a'), props: null, question_id: null, question_revision: null },
        { id: 20, composition_id: 9, sequence: 1, schema_version: 1, block_type: 'page_break', content: null, props: null, question_id: null, question_revision: null },
      ],
    }
    const next = reconcileAfterSave(prev, resp)
    expect(next[0]!.key).toBe('existing-key')
    expect(next[1]!.key).toBe('temp-key')
    expect(next[1]!.serverId).toBe(20)
    // 重建后快照应与保存前一致（内容未变），用于重置脏态。
    expect(snapshotBlocks(next)).toBe(snapshotBlocks(prev))
  })
})
