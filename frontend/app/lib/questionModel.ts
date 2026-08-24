import type {
    AnswerSpec,
    Blank,
    FillBlankAnswer,
    KnowledgePoint,
    OptionSpec,
    Question,
    QuestionStatus,
    QuestionType,
    RichDoc,
    Tag,
} from '@/types'
import { collectBlankIds, generateBlankId } from '@/components/rich-editor/richDoc'

/** 生成稳定唯一的 option id；优先 crypto.randomUUID，回退到时间戳+随机。 */
export function generateOptionId(): string {
    const g = globalThis as { crypto?: { randomUUID?: () => string } }
    if (g.crypto?.randomUUID) {
        return `opt_${g.crypto.randomUUID()}`
    }
    return `opt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

const OPTION_LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

export function nextOptionLabel(count: number): string {
    return OPTION_LABELS[count] ?? '?'
}

/** 新建默认 4 个空选项（含稳定 id）。 */
export function createDefaultOptions(): OptionSpec[] {
    return OPTION_LABELS.slice(0, 4).map((label) => ({
        id: generateOptionId(),
        label,
        content: null,
    }))
}

/**
 * 数据库编辑态草稿：所有富文本槽位为 RichDoc | null（对象，非字符串），
 * answer 为 AnswerSpec 判别联合，options 元素含稳定 id。
 */
export interface QuestionDraft {
    id?: number
    content: RichDoc
    q_type: QuestionType
    status: QuestionStatus
    difficulty: number
    options: OptionSpec[]
    answer: AnswerSpec | null
    thinking: RichDoc
    analysis: RichDoc
    summary: RichDoc
    source: string
    knowledge_point_ids: number[]
    tag_ids: number[]
    subject_id?: number
    parent_id?: number | null
}

export const CHOICE_TYPES: QuestionType[] = ['single_choice', 'multiple_choice']

export function isChoiceType(qType: QuestionType): boolean {
    return CHOICE_TYPES.includes(qType)
}

/** 用 stem 中的 blank 节点顺序构造填空 blanks；无 blank 节点时回退到一个空 blank。 */
export function fillBlanksFromStem(stem: RichDoc, prev?: Blank[]): Blank[] {
    const stemIds = collectBlankIds(stem)
    if (stemIds.length === 0) {
        // 迁移旧题干（无 blank 节点）：保留已有答案，至少给一个空 blank。
        if (prev && prev.length > 0) return prev
        return [{ id: generateBlankId(), accept: [null] }]
    }
    const byId = new Map((prev ?? []).map((b) => [b.id, b]))
    return stemIds.map((id) => byId.get(id) ?? { id, accept: [null] })
}

/** 为给定题型生成一个合法（或可继续编辑）的默认 answer。 */
export function createDefaultAnswer(
    qType: QuestionType,
    options: OptionSpec[],
    stem?: RichDoc,
): AnswerSpec {
    switch (qType) {
        case 'single_choice':
            return { kind: 'single_choice', correct: options[0]?.id ?? '' }
        case 'multiple_choice':
            return { kind: 'multiple_choice', correct: [] }
        case 'true_false':
            return { kind: 'true_false', correct: true }
        case 'fill_in_the_blank':
            return { kind: 'fill_in_the_blank', blanks: fillBlanksFromStem(stem ?? null) }
        case 'free_response':
            return { kind: 'free_response', reference: null }
    }
}

/** 新建空白数据库题目草稿（默认单选，含合法答案/选项）。 */
export function createEmptyDraft(opts: {
    subjectId?: number
    parentId?: number | null
} = {}): QuestionDraft {
    const options = createDefaultOptions()
    return {
        content: null,
        q_type: 'single_choice',
        status: 'draft',
        difficulty: 3,
        options,
        answer: createDefaultAnswer('single_choice', options),
        thinking: null,
        analysis: null,
        summary: null,
        source: '',
        knowledge_point_ids: [],
        tag_ids: [],
        subject_id: opts.subjectId,
        parent_id: opts.parentId ?? null,
    }
}

function cloneRich(doc: RichDoc | undefined): RichDoc {
    return doc ? (JSON.parse(JSON.stringify(doc)) as RichDoc) : null
}

/** 把 DB Question（或 decompose 的 Partial）映射为编辑草稿。 */
export function dbQuestionToDraft(
    q: Partial<Question>,
    opts: { subjectId?: number } = {},
): QuestionDraft {
    const qType = (q.q_type ?? 'single_choice') as QuestionType
    const options: OptionSpec[] = (q.options ?? []).map((o, i) => ({
        id: o.id || generateOptionId(),
        label: o.label || nextOptionLabel(i),
        content: cloneRich(o.content),
    }))
    const draft: QuestionDraft = {
        id: typeof q.id === 'number' ? q.id : undefined,
        content: cloneRich(q.content),
        q_type: qType,
        status: (q.status ?? 'draft') as QuestionStatus,
        difficulty: q.difficulty ?? 3,
        options,
        answer: q.answer ? (JSON.parse(JSON.stringify(q.answer)) as AnswerSpec) : null,
        thinking: cloneRich(q.thinking),
        analysis: cloneRich(q.analysis),
        summary: cloneRich(q.summary),
        source: q.source ?? '',
        knowledge_point_ids:
            (q.knowledge_points as KnowledgePoint[] | undefined)?.map((kp) => kp.id)
            ?? [],
        tag_ids: (q.tags as Tag[] | undefined)?.map((t) => t.id) ?? [],
        subject_id: q.subject_id ?? opts.subjectId,
        parent_id: q.parent_id ?? null,
    }
    // choice 题型缺省选项/答案时补齐，保证可编辑且合法。
    if (isChoiceType(qType) && draft.options.length === 0) {
        draft.options = createDefaultOptions()
    }
    if (!draft.answer) {
        draft.answer = createDefaultAnswer(qType, draft.options, draft.content)
    }
    return draft
}

/** 删除某个选项后，同步清除 answer 中对它的引用。 */
export function pruneAnswerOptionRef(answer: AnswerSpec | null, removedId: string): AnswerSpec | null {
    if (!answer) return answer
    if (answer.kind === 'single_choice' && answer.correct === removedId) {
        return { ...answer, correct: '' }
    }
    if (answer.kind === 'multiple_choice') {
        return { ...answer, correct: answer.correct.filter((id) => id !== removedId) }
    }
    return answer
}

export interface QuestionWritePayload {
    content: RichDoc
    q_type: QuestionType
    options: OptionSpec[] | null
    answer: AnswerSpec | null
    thinking: RichDoc
    analysis: RichDoc
    summary: RichDoc
    source: string | null
    difficulty: number
    knowledge_point_ids: number[]
    tag_ids: number[]
    status: QuestionStatus
    subject_id?: number
    parent_id: number | null
}

/** 构造发往后端的写请求 payload：直接传对象，不做任何 JSON.stringify。 */
export function buildQuestionPayload(draft: QuestionDraft): QuestionWritePayload {
    return {
        content: draft.content,
        q_type: draft.q_type,
        options: isChoiceType(draft.q_type) ? draft.options : null,
        answer: draft.answer,
        thinking: draft.thinking,
        analysis: draft.analysis,
        summary: draft.summary,
        source: draft.source || null,
        difficulty: draft.difficulty,
        knowledge_point_ids: draft.knowledge_point_ids,
        tag_ids: draft.tag_ids,
        status: draft.status,
        subject_id: draft.subject_id,
        parent_id: draft.parent_id ?? null,
    }
}

function isRichEmpty(doc: RichDoc): boolean {
    return !doc || !doc.content || doc.content.length === 0
}

/**
 * 提交前领域校验，返回第一条错误信息或 null（与后端 validate_question_domain 对齐）。
 * 阻止把非法答案（尤其 legacy_unresolved）发往严格 v2 后端。
 */
export function validateQuestionDraft(draft: QuestionDraft): string | null {
    if (isRichEmpty(draft.content)) {
        return '题干不能为空'
    }
    const answer = draft.answer
    if (!answer) {
        return '请填写答案'
    }
    if (answer.kind === 'legacy_unresolved') {
        return '该题为旧格式未解析答案，请重新填写答案后再保存'
    }
    if (answer.kind !== draft.q_type) {
        return '答案类型与题目类型不一致'
    }
    if (isChoiceType(draft.q_type)) {
        if (draft.options.length < 2) {
            return '选择题至少需要 2 个选项'
        }
        const ids = new Set(draft.options.map((o) => o.id))
        if (answer.kind === 'single_choice') {
            if (!answer.correct || !ids.has(answer.correct)) {
                return '请选择正确答案'
            }
        } else if (answer.kind === 'multiple_choice') {
            if (answer.correct.length === 0) {
                return '请至少选择一个正确答案'
            }
            if (answer.correct.some((id) => !ids.has(id))) {
                return '答案引用了不存在的选项'
            }
        }
    }
    if (answer.kind === 'fill_in_the_blank') {
        const err = validateFillBlanks(answer, draft.content)
        if (err) return err
    }
    return null
}

function validateFillBlanks(answer: FillBlankAnswer, stem: RichDoc): string | null {
    if (answer.blanks.length === 0) {
        return '填空题至少需要一个空'
    }
    for (let i = 0; i < answer.blanks.length; i++) {
        const accept = answer.blanks[i].accept.filter((a) => !isRichEmpty(a))
        if (accept.length === 0) {
            return `第 ${i + 1} 空至少需要一个参考答案`
        }
    }
    const stemIds = collectBlankIds(stem)
    if (stemIds.length > 0) {
        const answerIds = answer.blanks.map((b) => b.id)
        if (stemIds.length !== answerIds.length || stemIds.some((id, i) => id !== answerIds[i])) {
            return '题干填空与答案数量/顺序不一致'
        }
    }
    return null
}
