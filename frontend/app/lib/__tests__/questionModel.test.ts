import { describe, it, expect } from 'vitest'
import type { AnswerSpec, OptionSpec, RichDoc } from '@/types'
import { collectBlankIds, richDocToPlainText } from '@/components/rich-editor/richDoc'
import {
    createDefaultAnswer,
    createDefaultOptions,
    dbQuestionToDraft,
    fillBlanksFromStem,
    generateOptionId,
    pruneAnswerOptionRef,
    validateQuestionDraft,
    buildQuestionPayload,
    createEmptyDraft,
} from '@/lib/questionModel'
import { answerToPlainText, optionLabelsForAnswer } from '@/lib/answerFormat'

function doc(text: string): RichDoc {
    return { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function stemWithBlanks(...ids: string[]): RichDoc {
    return {
        type: 'doc',
        content: [
            {
                type: 'paragraph',
                content: ids.map((id) => ({ type: 'blank', attrs: { blankId: id } })),
            },
        ],
    }
}

describe('richDoc helpers', () => {
    it('collectBlankIds 按出现顺序收集', () => {
        expect(collectBlankIds(stemWithBlanks('b1', 'b2'))).toEqual(['b1', 'b2'])
        expect(collectBlankIds(null)).toEqual([])
        expect(collectBlankIds(doc('无空'))).toEqual([])
    })

    it('richDocToPlainText 抽纯文本，填空转下划线，公式取 latex', () => {
        expect(richDocToPlainText(doc('你好'))).toBe('你好')
        expect(richDocToPlainText(stemWithBlanks('b1'))).toBe('____')
        expect(richDocToPlainText(null)).toBe('')
        const math: RichDoc = {
            type: 'doc',
            content: [{ type: 'paragraph', content: [{ type: 'inlineMath', attrs: { latex: 'x^2' } }] }],
        }
        expect(richDocToPlainText(math)).toBe('x^2')
    })
})

describe('option / answer defaults', () => {
    it('generateOptionId 前缀 opt_ 且唯一', () => {
        const a = generateOptionId()
        const b = generateOptionId()
        expect(a.startsWith('opt_')).toBe(true)
        expect(a).not.toBe(b)
    })

    it('createDefaultOptions 生成 4 个带 id 的空选项', () => {
        const opts = createDefaultOptions()
        expect(opts).toHaveLength(4)
        expect(opts.map((o) => o.label)).toEqual(['A', 'B', 'C', 'D'])
        expect(new Set(opts.map((o) => o.id)).size).toBe(4)
        expect(opts.every((o) => o.content === null)).toBe(true)
    })

    it('createDefaultAnswer 按题型给合法默认值', () => {
        const opts = createDefaultOptions()
        expect(createDefaultAnswer('single_choice', opts)).toEqual({ kind: 'single_choice', correct: opts[0].id })
        expect(createDefaultAnswer('multiple_choice', opts)).toEqual({ kind: 'multiple_choice', correct: [] })
        expect(createDefaultAnswer('true_false', opts)).toEqual({ kind: 'true_false', correct: true })
        expect(createDefaultAnswer('free_response', opts)).toEqual({ kind: 'free_response', reference: null })
        const fill = createDefaultAnswer('fill_in_the_blank', opts)
        expect(fill.kind).toBe('fill_in_the_blank')
    })
})

describe('fillBlanksFromStem', () => {
    it('题干含 blank 节点时按其顺序同步，保留已有 accept', () => {
        const prev = [
            { id: 'b1', accept: [doc('答案1')] },
            { id: 'bx', accept: [doc('旧的')] },
        ]
        const synced = fillBlanksFromStem(stemWithBlanks('b2', 'b1'), prev)
        expect(synced.map((b) => b.id)).toEqual(['b2', 'b1'])
        // b1 的 accept 被保留
        expect(synced[1].accept).toEqual([doc('答案1')])
        // 新增的 b2 得到空 accept
        expect(synced[0].accept).toEqual([null])
    })

    it('题干无 blank 节点时保留原答案（迁移旧题）', () => {
        const prev = [{ id: 'old', accept: [doc('a')] }]
        expect(fillBlanksFromStem(doc('无空题干'), prev)).toBe(prev)
        // 无 prev 时回退到一个空 blank
        const fresh = fillBlanksFromStem(null)
        expect(fresh).toHaveLength(1)
        expect(fresh[0].accept).toEqual([null])
    })
})

describe('pruneAnswerOptionRef', () => {
    it('删除单选正确项后置空', () => {
        const a: AnswerSpec = { kind: 'single_choice', correct: 'opt_x' }
        expect(pruneAnswerOptionRef(a, 'opt_x')).toEqual({ kind: 'single_choice', correct: '' })
    })
    it('删除多选中的引用', () => {
        const a: AnswerSpec = { kind: 'multiple_choice', correct: ['opt_x', 'opt_y'] }
        expect(pruneAnswerOptionRef(a, 'opt_x')).toEqual({ kind: 'multiple_choice', correct: ['opt_y'] })
    })
})

describe('answer formatter', () => {
    const opts: OptionSpec[] = [
        { id: 'opt_a', label: 'A', content: doc('甲') },
        { id: 'opt_b', label: 'B', content: doc('乙') },
    ]
    it('optionLabelsForAnswer 映射 id → label', () => {
        expect(optionLabelsForAnswer({ kind: 'single_choice', correct: 'opt_b' }, opts)).toEqual(['B'])
        expect(optionLabelsForAnswer({ kind: 'multiple_choice', correct: ['opt_a', 'opt_b'] }, opts)).toEqual(['A', 'B'])
    })
    it('answerToPlainText 各题型', () => {
        expect(answerToPlainText({ kind: 'single_choice', correct: 'opt_a' }, opts)).toBe('A')
        expect(answerToPlainText({ kind: 'multiple_choice', correct: ['opt_a', 'opt_b'] }, opts)).toBe('A、B')
        expect(answerToPlainText({ kind: 'true_false', correct: false }, opts)).toBe('错误')
        expect(
            answerToPlainText(
                { kind: 'fill_in_the_blank', blanks: [{ id: 'b1', accept: [doc('x'), doc('y')] }] },
                null,
            ),
        ).toBe('x / y')
        expect(answerToPlainText({ kind: 'free_response', reference: doc('参考') }, null)).toBe('参考')
        expect(answerToPlainText(null, null)).toBe('')
    })
})

describe('validateQuestionDraft', () => {
    it('题干为空报错', () => {
        const d = createEmptyDraft()
        expect(validateQuestionDraft(d)).toBe('题干不能为空')
    })

    it('草稿允许答案为空或未完成', () => {
        const d = createEmptyDraft()
        d.content = doc('题干')
        expect(d.answer).toBeNull()
        expect(validateQuestionDraft(d)).toBeNull()
        d.answer = { kind: 'single_choice', correct: '' }
        expect(validateQuestionDraft(d)).toBeNull()
    })

    it('合法单选通过', () => {
        const d = createEmptyDraft()
        d.content = doc('题干')
        // 默认 answer 已指向第一个选项
        expect(validateQuestionDraft(d)).toBeNull()
    })

    it('pending 多选空集合报错', () => {
        const d = createEmptyDraft()
        d.content = doc('题干')
        d.q_type = 'multiple_choice'
        d.answer = { kind: 'multiple_choice', correct: [] }
        d.status = 'pending'
        expect(validateQuestionDraft(d)).toBe('请至少选择一个正确答案')
    })

    it('legacy_unresolved 被拒绝', () => {
        const d = createEmptyDraft()
        d.content = doc('题干')
        d.q_type = 'free_response'
        d.answer = { kind: 'legacy_unresolved', expected_kind: 'free_response', raw: doc('旧答案') }
        expect(validateQuestionDraft(d)).toContain('旧格式')
    })

    it('published 填空缺参考答案报错，且题干填空数量需匹配', () => {
        const d = createEmptyDraft()
        d.q_type = 'fill_in_the_blank'
        d.content = stemWithBlanks('b1', 'b2')
        d.answer = {
            kind: 'fill_in_the_blank',
            blanks: [
                { id: 'b1', accept: [null] },
                { id: 'b2', accept: [doc('x')] },
            ],
        }
        d.status = 'published'
        expect(validateQuestionDraft(d)).toBe('第 1 空至少需要一个参考答案')

        d.answer = {
            kind: 'fill_in_the_blank',
            blanks: [{ id: 'b1', accept: [doc('x')] }],
        }
        expect(validateQuestionDraft(d)).toBe('题干填空与答案数量/顺序不一致')
    })
})

describe('dbQuestionToDraft + buildQuestionPayload', () => {
    it('映射 DB 题目并生成对象 payload（不 stringify）', () => {
        const draft = dbQuestionToDraft({
            id: 7,
            content: doc('题干'),
            q_type: 'single_choice',
            options: [
                { id: 'opt_a', label: 'A', content: doc('甲') },
                { id: 'opt_b', label: 'B', content: doc('乙') },
            ],
            answer: { kind: 'single_choice', correct: 'opt_a' },
            knowledge_points: [{ id: 3, name: 'x', slug: 'x', subject_id: 1 }],
            tags: [{ id: 5, name: 't', category_id: null, color: '#000', subject_id: 1 }],
            subject_id: 1,
            difficulty: 4,
            status: 'published',
        })
        expect(draft.id).toBe(7)
        expect(draft.knowledge_point_ids).toEqual([3])
        expect(draft.tag_ids).toEqual([5])
        const payload = buildQuestionPayload(draft)
        expect(payload.answer).toEqual({ kind: 'single_choice', correct: 'opt_a' })
        expect(typeof payload.answer).toBe('object')
        expect(Array.isArray(payload.options)).toBe(true)
        // 非选择题时 options 为 null
        draft.q_type = 'free_response'
        expect(buildQuestionPayload(draft).options).toBeNull()
    })
})
