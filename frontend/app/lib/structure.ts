/**
 * 题干结构化的纯函数工具:类型树、领域配色、原文高亮分段。
 *
 * 不依赖 Vue / 网络,便于单元测试;组件与页面共用。
 */
import { translate } from '@/lib/locale'
import type { StructParamDomain, StructType, StructTypeKind, StructTypeStatus } from '~/types'

/** 类型编辑对话框提交的数据(新建时含 code;留空由后端按名称生成)。 */
export interface StructTypeFormValue {
  name: string
  code: string
  definition: string
  examples: Array<{ text: string, positive: boolean }>
  status: StructTypeStatus
  /** 思维量权重(方法类型)。 */
  weight: number
  /** 映射的知识点。 */
  knowledge_point_ids: number[]
}

/** 类型树节点:在扁平的 StructType 上挂子节点。 */
export interface StructTypeNode extends StructType {
  children: StructTypeNode[]
  /** 从根到自身的深度(根为 0)。 */
  depth: number
}

/** 领域(类型树第一层)的配色;按根节点的顺序循环使用,设问统一用中性色。 */
const DOMAIN_CLASSES = [
  { text: 'text-sky-700 dark:text-sky-300', bg: 'bg-sky-500/15', border: 'border-sky-500/40', dot: 'bg-sky-500' },
  { text: 'text-emerald-700 dark:text-emerald-300', bg: 'bg-emerald-500/15', border: 'border-emerald-500/40', dot: 'bg-emerald-500' },
  { text: 'text-amber-700 dark:text-amber-300', bg: 'bg-amber-500/15', border: 'border-amber-500/40', dot: 'bg-amber-500' },
  { text: 'text-fuchsia-700 dark:text-fuchsia-300', bg: 'bg-fuchsia-500/15', border: 'border-fuchsia-500/40', dot: 'bg-fuchsia-500' },
]
const ASK_CLASSES = { text: 'text-violet-700 dark:text-violet-300', bg: 'bg-violet-500/15', border: 'border-violet-500/40', dot: 'bg-violet-500' }
const NEUTRAL_CLASSES = { text: 'text-muted-foreground', bg: 'bg-muted', border: 'border-border', dot: 'bg-muted-foreground' }

export type DomainClasses = typeof NEUTRAL_CLASSES

/** 扁平类型列表 → 森林(按 sort_order、id 排序);可按 kind 过滤。 */
export function buildStructTypeTree(types: StructType[], kind?: StructTypeKind): StructTypeNode[] {
  const list = kind ? types.filter(t => t.kind === kind) : types
  const nodes = new Map<number, StructTypeNode>()
  for (const t of list) nodes.set(t.id, { ...t, children: [], depth: 0 })
  const roots: StructTypeNode[] = []
  for (const node of nodes.values()) {
    const parent = node.parent_id != null ? nodes.get(node.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const order = (a: StructTypeNode, b: StructTypeNode) => a.sort_order - b.sort_order || a.id - b.id
  const walk = (items: StructTypeNode[], depth: number) => {
    items.sort(order)
    for (const item of items) {
      item.depth = depth
      walk(item.children, depth + 1)
    }
  }
  walk(roots, 0)
  return roots
}

/** 深度优先展开为带深度的列表(下拉选择、表格用)。 */
export function flattenStructTypeTree(roots: StructTypeNode[]): StructTypeNode[] {
  const out: StructTypeNode[] = []
  const walk = (items: StructTypeNode[]) => {
    for (const item of items) {
      out.push(item)
      walk(item.children)
    }
  }
  walk(roots)
  return out
}

/** 给定节点及其全部子孙的 id(筛选时选中「代数」也要命中其下的类型)。 */
export function structTypeDescendants(types: StructType[], rootIds: number[]): Set<number> {
  const children = new Map<number | null, number[]>()
  for (const t of types) {
    const list = children.get(t.parent_id) ?? []
    list.push(t.id)
    children.set(t.parent_id, list)
  }
  const found = new Set<number>()
  const stack = [...rootIds]
  while (stack.length) {
    const id = stack.pop()!
    if (found.has(id)) continue
    found.add(id)
    stack.push(...(children.get(id) ?? []))
  }
  return found
}

/** 类型所在的根节点(领域)。 */
export function structTypeRoot(types: StructType[], typeId: number | null | undefined): StructType | undefined {
  if (typeId == null) return undefined
  const byId = new Map(types.map(t => [t.id, t]))
  let current = byId.get(typeId)
  let guard = 0
  while (current?.parent_id != null && guard < 64) {
    const parent = byId.get(current.parent_id)
    if (!parent) break
    current = parent
    guard += 1
  }
  return current
}

/** 某个类型(按其所在领域)的配色;未归类为中性色,设问为统一的紫色。 */
export function domainClasses(types: StructType[], typeId: number | null | undefined): DomainClasses {
  const root = structTypeRoot(types, typeId)
  if (!root) return NEUTRAL_CLASSES
  if (root.kind === 'ask') return ASK_CLASSES
  const conditionRoots = buildStructTypeTree(types, 'condition')
  const index = conditionRoots.findIndex(r => r.id === root.id)
  return DOMAIN_CLASSES[(index < 0 ? 0 : index) % DOMAIN_CLASSES.length]!
}

/** 原文中的一段:纯文本,或被若干条目引用的高亮段。 */
export interface StemSegment {
  text: string
  start: number
  end: number
  /** 覆盖这一段的条目 key,如 "e:12"(条件)、"a:3"(设问)。 */
  keys: string[]
}

/**
 * 按条目的原文区间把题干切成连续的段;区间可以重叠,重叠处的 keys 同时包含多条。
 *
 * @param text 拆解快照的 stem_text
 * @param ranges 条目区间:{ key, span: [start, end) }
 */
export function segmentStem(text: string, ranges: Array<{ key: string, span: [number, number] | null }>): StemSegment[] {
  const valid = ranges.filter(r => r.span && r.span[0] < r.span[1] && r.span[0] >= 0 && r.span[1] <= text.length)
  const cuts = new Set<number>([0, text.length])
  for (const r of valid) {
    cuts.add(r.span![0])
    cuts.add(r.span![1])
  }
  const points = [...cuts].sort((a, b) => a - b)
  const segments: StemSegment[] = []
  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i]!
    const end = points[i + 1]!
    if (start === end) continue
    const keys = valid.filter(r => r.span![0] <= start && r.span![1] >= end).map(r => r.key)
    segments.push({ text: text.slice(start, end), start, end, keys })
  }
  return segments
}

/**
 * 把一段可能含 $...$ 公式的文本拆成文字与公式两种片段,供渲染(公式交给 KaTeX)。
 * 未闭合的 $ 按普通文字处理。
 */
export function splitMath(text: string): Array<{ math: boolean, display: boolean, value: string }> {
  const parts: Array<{ math: boolean, display: boolean, value: string }> = []
  const pattern = /\$\$([\s\S]+?)\$\$|\$([^$]+?)\$/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push({ math: false, display: false, value: text.slice(last, match.index) })
    const display = match[1] !== undefined
    parts.push({ math: true, display, value: (display ? match[1] : match[2]) ?? '' })
    last = pattern.lastIndex
  }
  if (last < text.length) parts.push({ math: false, display: false, value: text.slice(last) })
  return parts
}

/** 原文渲染单元:一段文字或一个完整公式,带绝对偏移与覆盖它的条目。 */
export interface StemToken {
  start: number
  end: number
  /** 是否公式;公式整体渲染、整体高亮,不会被区间切开。 */
  math: boolean
  display: boolean
  /** 文字原文,或公式的 LaTeX(不含 $)。 */
  value: string
  /** 覆盖(与之重叠)这一单元的条目 key。 */
  keys: string[]
}

/**
 * 把题干切成渲染单元:先按 $...$ 切出公式(公式是原子单元,任何区间边界落在公式内部都不切它),
 * 再把文字部分按条目区间切开。这样既能逐段高亮,又不会把一个公式拆成两半导致 KaTeX 渲染失败。
 */
export function stemTokens(text: string, ranges: Array<{ key: string, span: [number, number] | null }>): StemToken[] {
  const valid = ranges.filter(r => r.span && r.span[0] < r.span[1] && r.span[0] >= 0 && r.span[1] <= text.length)
  // 与 [start, end) 有重叠的条目。
  const keysFor = (start: number, end: number) =>
    valid.filter(r => r.span![0] < end && r.span![1] > start).map(r => r.key)
  const tokens: StemToken[] = []
  let offset = 0
  for (const part of splitMath(text)) {
    // splitMath 不返回原始长度,这里按定界符还原:公式占 value + 两侧的 $ / $$。
    const delimiter = part.math ? (part.display ? 2 : 1) : 0
    const length = part.value.length + delimiter * 2
    const start = offset
    const end = offset + length
    offset = end
    if (part.math) {
      tokens.push({ start, end, math: true, display: part.display, value: part.value, keys: keysFor(start, end) })
      continue
    }
    // 文字部分:在落入其中的区间边界处切开。
    const cuts = new Set<number>([start, end])
    for (const r of valid) {
      for (const point of r.span!) if (point > start && point < end) cuts.add(point)
    }
    const points = [...cuts].sort((a, b) => a - b)
    for (let i = 0; i < points.length - 1; i += 1) {
      const from = points[i]!
      const to = points[i + 1]!
      tokens.push({
        start: from,
        end: to,
        math: false,
        display: false,
        value: text.slice(from, to),
        keys: valid.filter(r => r.span![0] <= from && r.span![1] >= to).map(r => r.key),
      })
    }
  }
  return tokens
}

/**
 * 把选区的一端换算成 stem_text 中的偏移。
 *
 * @param token 选区端点所在的渲染单元
 * @param innerOffset 端点在该单元文字内的偏移(公式单元忽略)
 * @param edge 选区的起点还是终点:落在公式里时,起点吸附到公式开头、终点吸附到公式结尾,
 *   这样选中半个公式也会得到完整的公式原文。
 */
export function tokenOffset(token: StemToken, innerOffset: number, edge: 'start' | 'end'): number {
  if (token.math) return edge === 'start' ? token.start : token.end
  return Math.min(token.end, Math.max(token.start, token.start + innerOffset))
}

/**
 * 按名称 / 编码过滤类型树:保留命中的节点,以及它们的全部祖先(否则命中的子类型会失去上下文);
 * 命中节点的子孙不再继续展开过滤,原样保留,便于看到其下的细分。
 */
export function filterStructTypeTree(roots: StructTypeNode[], query: string): StructTypeNode[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return roots
  const matches = (node: StructTypeNode) =>
    node.name.toLowerCase().includes(needle) || node.code.toLowerCase().includes(needle)
  const walk = (nodes: StructTypeNode[]): StructTypeNode[] => {
    const out: StructTypeNode[] = []
    for (const node of nodes) {
      if (matches(node)) {
        out.push(node)
        continue
      }
      // 自身不命中:只有当某个子孙命中时才保留,并且只带上命中的那几支。
      const children = walk(node.children)
      if (children.length) out.push({ ...node, children })
    }
    return out
  }
  return walk(roots)
}

/**
 * 在 text[within] 中找 value 的第 occurrence 次「独立」出现(与后端 params.locate_value 一致):
 * 数字前后不能紧挨数字、小数点,也不能是上下标(x^2 里的 2);字母前后不能紧挨字母或属于 LaTeX 命令。
 */
export function locateParamValue(
  text: string,
  value: string,
  within: [number, number],
  occurrence = 1,
): [number, number] | null {
  if (!value) return null
  const hits: Array<[number, number]> = []
  let position = text.indexOf(value, within[0])
  while (position !== -1 && position + value.length <= within[1]) {
    if (isStandalone(text, position, position + value.length)) hits.push([position, position + value.length])
    position = text.indexOf(value, position + 1)
  }
  return hits[Math.max(occurrence, 1) - 1] ?? null
}

function isStandalone(text: string, start: number, end: number): boolean {
  const first = text[start]!
  const last = text[end - 1]!
  const before = start > 0 ? text[start - 1]! : ''
  const after = end < text.length ? text[end]! : ''
  const digit = (c: string) => /\d/.test(c)
  const alpha = (c: string) => /[A-Za-z]/.test(c)
  if (digit(first) || first === '.') {
    if (before && (digit(before) || '.^_'.includes(before))) return false
    if (before === '{' && start >= 2 && '^_'.includes(text[start - 2]!)) return false
  }
  if (alpha(first) && before && (alpha(before) || /\\[A-Za-z]*$/.test(text.slice(0, start)))) return false
  if (digit(last) && after && (digit(after) || after === '.')) return false
  if (alpha(last) && after && alpha(after)) return false
  return true
}

/** 按区间替换文本(从后往前,互不影响),用于预览变式题干。重叠或越界的区间忽略。 */
export function replaceSpans(text: string, replacements: Array<{ span: [number, number], value: string }>): string {
  const ordered = [...replacements]
    .filter(r => r.span[0] >= 0 && r.span[0] < r.span[1] && r.span[1] <= text.length)
    .sort((a, b) => b.span[0] - a.span[0])
  let out = text
  let limit = text.length
  for (const item of ordered) {
    if (item.span[1] > limit) continue
    out = out.slice(0, item.span[0]) + item.value + out.slice(item.span[1])
    limit = item.span[0]
  }
  return out
}

/** 区间是否落在某个公式内部(参数值是 LaTeX,展示时需要包上 $)。 */
export function spanInMath(text: string, span: [number, number]): boolean {
  return stemTokens(text, []).some(token => token.math && token.start < span[0] && span[1] < token.end)
}

/** 取值范围的简短说明,例如「1 ~ 9 · 整数」;为空时返回空串。 */
export function formatParamDomain(domain: StructParamDomain | null | undefined): string {
  if (!domain) return ''
  const parts: string[] = []
  if (domain.min != null || domain.max != null) parts.push(`${domain.min ?? '-∞'} ~ ${domain.max ?? '+∞'}`)
  if (domain.integer) parts.push(translate('structure.params.integer'))
  if (domain.values?.length) parts.push(domain.values.join(' / '))
  if (domain.exclude?.length) parts.push(translate('structure.params.excludeList', { values: domain.exclude.join(', ') }))
  if (domain.note) parts.push(domain.note)
  return parts.join(' · ')
}
