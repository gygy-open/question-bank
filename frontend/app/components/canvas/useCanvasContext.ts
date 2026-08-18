import type { InjectionKey } from 'vue'
import type { DisplayPolicy } from '~/types'

export interface CanvasContext {
  /** 文档级显示策略, 题块据此与自身覆盖级联解析有效策略。 */
  documentDisplay: DisplayPolicy | null
  /** 当前组稿 id，用于克隆时排除自身。 */
  compId?: number
}

export const CanvasContextKey: InjectionKey<CanvasContext> = Symbol('CanvasContext')
