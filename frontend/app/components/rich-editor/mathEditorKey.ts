import type { InjectionKey } from 'vue'

export interface OpenMathEditorParams {
    pos: number
    isBlock: boolean
    latex: string
    anchorEl: HTMLElement | null
}

export type OpenMathEditor = (params: OpenMathEditorParams) => void

/** 由 RichEditor 提供、公式 nodeView 注入，用于打开外部（脱离 ProseMirror 的）MathLive 编辑浮层。 */
export const MATH_EDITOR_KEY: InjectionKey<OpenMathEditor> = Symbol('richMathEdit')
