import type { InjectionKey } from 'vue'

export interface OpenBlankEditorParams {
    pos: number
    widthEm: number
    anchorEl: HTMLElement | null
}

export type OpenBlankEditor = (params: OpenBlankEditorParams) => void

/** 由 RichEditor 提供、填空 nodeView 注入,用于打开调整填空长度的外部浮层。 */
export const BLANK_EDITOR_KEY: InjectionKey<OpenBlankEditor> = Symbol('richBlankEdit')
