import type { InjectionKey } from 'vue'

export interface CanvasContext {
  /** 题块是否展示答案/解析 (由文档级设置 show_answers 决定)。 */
  showAnswers: boolean
  /** 当前组稿 id，用于克隆时排除自身。 */
  compId?: number
}

export const CanvasContextKey: InjectionKey<CanvasContext> = Symbol('CanvasContext')
