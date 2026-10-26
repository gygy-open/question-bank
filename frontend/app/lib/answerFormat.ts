import type { AnswerSpec, OptionSpec, QuestionType } from '@/types'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'
import { translate } from '@/lib/locale'

/** 单选/多选题：把 answer 引用的 option id 映射为可读 label（找不到时回退 id）。 */
export function optionLabelsForAnswer(
    answer: AnswerSpec | null | undefined,
    options: OptionSpec[] | null | undefined,
): string[] {
    if (!answer) return []
    const byId = new Map((options ?? []).map((o) => [o.id, o.label]))
    if (answer.kind === 'single_choice') {
        return answer.correct ? [byId.get(answer.correct) ?? answer.correct] : []
    }
    if (answer.kind === 'multiple_choice') {
        return answer.correct.map((id) => byId.get(id) ?? id)
    }
    return []
}

/** 选项匹配：按空位顺序得到 { 空位序号或稿件题号, 选项 label }，未选为空串。 */
export function matchingAnswerEntries(
    answer: AnswerSpec | null | undefined,
    options: OptionSpec[] | null | undefined,
    numbers?: Record<string, string | undefined>,
): { number: string; label: string }[] {
    if (answer?.kind !== 'option_matching') return []
    const byId = new Map((options ?? []).map((o) => [o.id, o.label]))
    return answer.slots.map((slot, i) => ({
        number: numbers?.[slot.id] || String(i + 1),
        label: slot.correct ? (byId.get(slot.correct) ?? slot.correct) : '',
    }))
}

/**
 * 把 AnswerSpec 抽成纯文本摘要（列表卡片/预览用），不渲染富文本，只取纯文本。
 * 空答案返回 ''。
 */
export function answerToPlainText(
    answer: AnswerSpec | null | undefined,
    options: OptionSpec[] | null | undefined,
): string {
    if (!answer) return ''
    switch (answer.kind) {
        case 'single_choice':
        case 'multiple_choice':
            return optionLabelsForAnswer(answer, options).join('、')
        case 'true_false':
            return answer.correct ? '正确' : '错误'
        case 'fill_in_the_blank':
            return answer.blanks
                .map((b) => b.accept.map((a) => richDocToPlainText(a)).filter(Boolean).join(' / '))
                .join('；')
        case 'free_response':
            return richDocToPlainText(answer.reference)
        case 'option_matching':
            return matchingAnswerEntries(answer, options)
                .map((entry) => `${entry.number}. ${entry.label || '？'}`)
                .join('；')
        case 'legacy_unresolved':
            return richDocToPlainText(answer.raw)
        default:
            return ''
    }
}

// 中文题型名属于内容语言：questionTypeLabel 也被稿件大纲（喂给 AI 模型）使用，保持原样。
// 界面展示请用 questionTypeLabelKey + t()。
const TYPE_LABELS: Record<QuestionType, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_in_the_blank: '填空题',
    free_response: '解答题',
    option_matching: '选项匹配',
}

export function questionTypeLabel(qType: QuestionType | string): string {
    return TYPE_LABELS[qType as QuestionType] ?? String(qType)
}

const TYPE_LABEL_KEYS: Record<QuestionType, string> = {
    single_choice: 'questions.types.singleChoice',
    multiple_choice: 'questions.types.multipleChoice',
    true_false: 'questions.types.trueFalse',
    fill_in_the_blank: 'questions.types.fillInTheBlank',
    free_response: 'questions.types.freeResponse',
    option_matching: 'questions.types.optionMatching',
}

/** 题型的 i18n key（界面展示用）；未知题型返回 null，调用方回退原值。 */
export function questionTypeLabelKey(qType: QuestionType | string): string | null {
    return TYPE_LABEL_KEYS[qType as QuestionType] ?? null
}

/** 题型的界面显示名（随界面语言），供组件模板直接调用。 */
export function questionTypeDisplayLabel(qType: QuestionType | string): string {
    const key = questionTypeLabelKey(qType)
    return key ? translate(key) : String(qType)
}
