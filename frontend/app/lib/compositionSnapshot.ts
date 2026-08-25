// 组稿版本 snapshot 只读纯函数：仅消费冻结快照，不查询当前题库。
// 与后端 _build_snapshot 语义对齐；answer_summary 的 resolved_question_ids 已由服务端
// 按 sequence 去重保序固化（all/before 语义），前端只按该顺序映射到快照题目。

import type {
  CompositionSnapshotV1,
  QuestionSnapshot,
  SnapshotAnswerSummaryBlock,
  SnapshotQuestionBlock,
} from '@/types/composition'

/**
 * 建立 question_id → QuestionSnapshot 映射，仅收录含内嵌 question 的 question block。
 * 同一 question_id 多次出现时保留首个（与去重保序一致）。
 */
export function snapshotQuestionMap(
  snapshot: CompositionSnapshotV1,
): Map<number, QuestionSnapshot> {
  const map = new Map<number, QuestionSnapshot>()
  for (const block of snapshot.blocks) {
    if (block.block_type !== 'question') continue
    const q = (block as SnapshotQuestionBlock).question
    if (q && !map.has(q.id)) {
      map.set(q.id, q)
    }
  }
  return map
}

/**
 * 按 answer_summary 的 resolved_question_ids 顺序，从同一 snapshot 的 question 映射解析题目。
 * 缺失内容（题目在定稿时已删除）的 id 被跳过；顺序严格保持 resolved ids 的顺序。
 */
export function resolveSummaryQuestions(
  snapshot: CompositionSnapshotV1,
  block: SnapshotAnswerSummaryBlock,
  questionMap?: Map<number, QuestionSnapshot>,
): QuestionSnapshot[] {
  const map = questionMap ?? snapshotQuestionMap(snapshot)
  const out: QuestionSnapshot[] = []
  for (const id of block.resolved_question_ids) {
    const q = map.get(id)
    if (q) out.push(q)
  }
  return out
}
