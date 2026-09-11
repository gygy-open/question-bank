// 稿件大纲投影 —— 喂给模型「它能看见什么」。
//
// 不能把原始 AST 丢给模型：question 节点的 content 是几千 token 的冻结快照。这里只留
// 节点 id、类型、关键属性与内容摘要，上下文成本降一两个数量级。
//
// **必须表达 module 的嵌套**，不能拍平成一维列表 —— 否则「在第一题后面插入」会有锚点歧义
// （插在 module 之后还是 question 之后）。

import type { AnswerFieldKey } from '@/types/composition'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'
import { questionTypeLabel } from '@/lib/answerFormat'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import {
  answerSpacePropsOf,
  detailPropsOf,
  headingLevelOf,
  questionNumberOf,
  questionScoreOf,
  questionShowOverride,
} from '@/lib/compositionDocument'

const SUMMARY_LIMIT = 60

export const FIELD_LABELS: Record<AnswerFieldKey, string> = {
  answer: '答案',
  thinking: '思路',
  analysis: '解析',
  summary: '小结',
}

export function truncate(text: string, limit = SUMMARY_LIMIT): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat
}

/** 节点的人话名称，用于变更清单；不含 id。 */
export function describeNode(node: EditorNode): string {
  switch (node.nodeType) {
    case 'heading':
      return `${headingLevelOf(node)} 级标题「${truncate(richDocToPlainText(node.content), 40)}」`
    case 'rich_text':
      return `文本「${truncate(richDocToPlainText(node.content), 40)}」`
    case 'question': {
      const number = questionNumberOf(node)
      const stem = truncate(richDocToPlainText(node.questionContent?.content ?? null), 40)
      return number ? `第 ${number} 题「${stem}」` : `题目「${stem}」`
    }
    case 'question_details':
      return `参考答案模块（${detailPropsOf(node).scope === 'all' ? '全稿' : '模块之前'}）`
    case 'answer_space': {
      const props = answerSpacePropsOf(node)
      return `作答空间（${props.lines} 行${props.style === 'lined' ? '横线' : '空白'}）`
    }
    case 'page_break':
      return '分页符'
    case 'answer_item':
      return '答案条目'
  }
}

function questionLine(node: EditorNode): string {
  const parts: string[] = [`question #${node.questionId ?? '?'}`]
  const snapshot = node.questionContent
  if (snapshot?.q_type) parts.push(questionTypeLabel(snapshot.q_type))
  const number = questionNumberOf(node)
  if (number) parts.push(`题号${number}`)
  const score = questionScoreOf(node)
  if (score != null) parts.push(`${score}分`)
  const overrides = ANSWER_FIELD_KEYS
    .map((key) => {
      const v = questionShowOverride(node, key)
      return v == null ? null : `${v ? '显示' : '隐藏'}${FIELD_LABELS[key]}`
    })
    .filter(Boolean)
  if (overrides.length) parts.push(overrides.join('/'))
  parts.push(`「${truncate(richDocToPlainText(snapshot?.content ?? null))}」`)
  return parts.join(' ')
}

function nodeLine(node: EditorNode): string {
  switch (node.nodeType) {
    case 'heading':
      return `heading(h${headingLevelOf(node)}) 「${truncate(richDocToPlainText(node.content))}」`
    case 'rich_text':
      return `text 「${truncate(richDocToPlainText(node.content))}」`
    case 'question':
      return questionLine(node)
    case 'page_break':
      return 'page_break'
    case 'answer_space': {
      const props = answerSpacePropsOf(node)
      return `answer_space ${props.lines}行 ${props.style}`
    }
    case 'question_details': {
      const props = detailPropsOf(node)
      const on = ANSWER_FIELD_KEYS.filter((k) => props.fields[k]).map((k) => FIELD_LABELS[k])
      return `question_details 收录=${props.scope} 展示=${on.length ? on.join('/') : '无'}`
    }
    case 'answer_item':
      return `answer_item ← ${node.sourceQuestionNodeId ?? '?'}`
  }
}

export interface OutlineContext {
  title: string
  /** 稿件级字段显隐默认值；题目级 show 覆盖缺省时回落到它。 */
  questionDisplay: Record<AnswerFieldKey, boolean>
  numberingEnabled: boolean
  scoringEnabled: boolean
}

/** 渲染成喂给模型的纯文本大纲。 */
export function renderOutline(doc: EditorDocument, ctx: OutlineContext): string {
  const globals = ANSWER_FIELD_KEYS
    .filter((k) => ctx.questionDisplay[k])
    .map((k) => FIELD_LABELS[k])
  const lines: string[] = [
    `稿件《${ctx.title}》 共 ${doc.nodes.length} 个顶层节点`,
    `全局设置：题号${ctx.numberingEnabled ? '开' : '关'}、`
      + `分值${ctx.scoringEnabled ? '开' : '关'}、`
      + `默认展示${globals.length ? globals.join('/') : '无'}`,
  ]
  if (!doc.nodes.length) {
    lines.push('（稿件是空的，还没有任何内容）')
    return lines.join('\n')
  }
  lines.push('')
  for (const node of doc.nodes) {
    lines.push(`[${node.id}] ${nodeLine(node)}`)
    // 子节点缩进表达从属关系：拍平会让「插到第一题后面」分不清落点。
    for (const child of node.children) {
      lines.push(`    └ [${child.id}] ${nodeLine(child)}`)
    }
  }
  return lines.join('\n')
}
