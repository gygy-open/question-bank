/** 题目查重:与后端 app/services/question_dedup.py 的 DuplicateCandidate 对齐。 */

export const DUPLICATE_CODE = 'question.duplicate_suspected'

export interface DuplicateDiff {
  before: string
  existing: string
  incoming: string
  after: string
}

export interface DuplicateCandidate {
  question_id: number
  level: 'duplicate' | 'similar'
  similarity: number
  /** 数字或公式不同,可能是变式题 */
  variant: boolean
  preview: string
  q_type: string
  status: string
  created_by: string | null
  created_at: string | null
  diff: DuplicateDiff[]
}

export interface IntraBatchDuplicate {
  ref: string
  level: 'duplicate' | 'similar'
  similarity: number
}

interface ErrorBody {
  code?: string
  params?: { candidates?: DuplicateCandidate[] }
}

/** 409 查重错误里的候选;不是查重错误返回 null。 */
export function duplicateCandidatesFromError(error: unknown): DuplicateCandidate[] | null {
  const e = error as { data?: ErrorBody, response?: { _data?: ErrorBody } }
  const body = e?.data ?? e?.response?._data
  if (body?.code !== DUPLICATE_CODE) return null
  return body.params?.candidates ?? []
}

/** 候选里最强的级别:有任一「重复」即为 duplicate。 */
export function strongestLevel(candidates: DuplicateCandidate[]): 'duplicate' | 'similar' | null {
  if (!candidates.length) return null
  return candidates.some(c => c.level === 'duplicate') ? 'duplicate' : 'similar'
}

export function similarityPercent(value: number): number {
  return Math.round(value * 100)
}
