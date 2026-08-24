// 富文本原子模型（题目内容 v2）。与后端 RichDoc 契约一致：根节点 type 恒为 'doc'。
// 编辑器输出、只读渲染、领域校验共用同一套结构，禁止在此引入 any。

export interface RichMark {
  type: string
  attrs?: Record<string, unknown>
}

export interface RichNode {
  type: string
  attrs?: Record<string, unknown>
  content?: RichNode[]
  marks?: RichMark[]
  text?: string
}

export interface RichDocNode {
  type: 'doc'
  content?: RichNode[]
}

/** 富文本槽位统一类型：要么是合法 doc，要么为空（null）。不存空 doc。 */
export type RichDoc = RichDocNode | null
