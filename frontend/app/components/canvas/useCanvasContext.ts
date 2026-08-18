import type { InjectionKey } from 'vue'
import type { CompType } from '~/types'

export interface CanvasContext {
  /** 当前组稿版式，用于块的展示适配 (试卷/学案/题组)。 */
  pubType: CompType
  /** 题块是否展示答案/解析 (学案、题组默认 true；试卷编辑默认 false)。 */
  showAnswers: boolean
  /** 当前组稿 id，用于搜索教学模块时排除自身 (防止自我引用)。 */
  compId?: number
}

export const CanvasContextKey: InjectionKey<CanvasContext> = Symbol('CanvasContext')
