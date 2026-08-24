import type { AnswerSpec, OptionSpec, QuestionType } from '@/types'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'

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
        case 'legacy_unresolved':
            return richDocToPlainText(answer.raw)
        default:
            return ''
    }
}

const TYPE_LABELS: Record<QuestionType, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_in_the_blank: '填空题',
    free_response: '解答题',
}

export function questionTypeLabel(qType: QuestionType | string): string {
    return TYPE_LABELS[qType as QuestionType] ?? String(qType)
}
