import type { InjectionKey } from 'vue'
import type { PublicationType } from '~/types'

export interface CanvasContext {
  /** 当前出版物类型，用于块的展示适配 (试卷/学案/题组)。 */
  pubType: PublicationType
  /** 题块是否展示答案/解析 (学案、题组默认 true；试卷编辑默认 false)。 */
  showAnswers: boolean
}

export const CanvasContextKey: InjectionKey<CanvasContext> = Symbol('CanvasContext')
