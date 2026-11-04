import { describe, expect, it } from 'vitest'
import {
  buildStructTypeTree,
  domainClasses,
  filterStructTypeTree,
  flattenStructTypeTree,
  segmentStem,
  splitMath,
  structTypeDescendants,
  stemTokens,
  structTypeRoot,
  tokenOffset,
} from '@/lib/structure'
import type { StructType } from '~/types'

const type = (id: number, parent: number | null, kind: 'condition' | 'ask', order = 0): StructType => ({
  id, subject_id: 1, parent_id: parent, kind, code: `t${id}`, name: `T${id}`, definition: null,
  examples: null, status: 'active', sort_order: order, usage: 0,
})

// 代数(1) > 函数(4) > 三次函数(5);几何(2);设问(3) > 求范围(6)
const TYPES = [type(1, null, 'condition', 0), type(2, null, 'condition', 1), type(3, null, 'ask', 2),
  type(4, 1, 'condition'), type(5, 4, 'condition'), type(6, 3, 'ask')]

describe('buildStructTypeTree', () => {
  it('nests by parent and keeps sort order, optionally per kind', () => {
    const roots = buildStructTypeTree(TYPES)
    expect(roots.map(r => r.id)).toEqual([1, 2, 3])
    expect(flattenStructTypeTree(roots).map(n => [n.id, n.depth])).toEqual([[1, 0], [4, 1], [5, 2], [2, 0], [3, 0], [6, 1]])
    expect(buildStructTypeTree(TYPES, 'ask').map(r => r.id)).toEqual([3])
  })
})

describe('structTypeDescendants / structTypeRoot', () => {
  it('expands a domain to everything beneath it', () => {
    expect([...structTypeDescendants(TYPES, [1])].sort()).toEqual([1, 4, 5])
    expect(structTypeRoot(TYPES, 5)?.id).toBe(1)
    expect(structTypeRoot(TYPES, null)).toBeUndefined()
  })

  it('colours conditions by domain and asks uniformly', () => {
    expect(domainClasses(TYPES, 5)).toEqual(domainClasses(TYPES, 1))
    expect(domainClasses(TYPES, 2)).not.toEqual(domainClasses(TYPES, 1))
    expect(domainClasses(TYPES, 6).text).toContain('violet')
    expect(domainClasses(TYPES, null).text).toBe('text-muted-foreground')
  })
})

describe('segmentStem', () => {
  it('cuts the stem at span boundaries and keeps overlaps', () => {
    const text = 'abcdefgh'
    const segments = segmentStem(text, [
      { key: 'e:1', span: [1, 5] },
      { key: 'e:2', span: [3, 6] },
      { key: 'a:1', span: null },
      { key: 'bad', span: [6, 99] },
    ])
    expect(segments.map(s => [s.text, s.keys])).toEqual([
      ['a', []], ['bc', ['e:1']], ['de', ['e:1', 'e:2']], ['f', ['e:2']], ['gh', []],
    ])
    expect(segments.map(s => s.text).join('')).toBe(text)
  })
})

describe('splitMath', () => {
  it('separates inline and display math from text', () => {
    expect(splitMath('已知$f(x)$有$$y=1$$个 $未闭合')).toEqual([
      { math: false, display: false, value: '已知' },
      { math: true, display: false, value: 'f(x)' },
      { math: false, display: false, value: '有' },
      { math: true, display: true, value: 'y=1' },
      { math: false, display: false, value: '个 $未闭合' },
    ])
  })
})

describe('stemTokens / tokenOffset', () => {
  it('keeps formulas whole even when a span boundary falls inside', () => {
    const text = '已知$f(x)=x^2$有$a$'
    const fEnd = text.indexOf('有')
    const tokens = stemTokens(text, [
      { key: 'e:1', span: [2, 6] },           // 边界落在第一个公式内部
      { key: 'a:1', span: [fEnd, text.length] },
    ])
    expect(tokens.map(t => [t.value, t.math, t.keys])).toEqual([
      ['已知', false, []],
      ['f(x)=x^2', true, ['e:1']],
      ['有', false, ['a:1']],
      ['a', true, ['a:1']],
    ])
    expect(tokens.at(-1)!.end).toBe(text.length)
  })

  it('snaps selection ends inside a formula to its edges', () => {
    const [, formula, plain] = stemTokens('已知$x>0$求', [])
    expect(tokenOffset(formula!, 3, 'start')).toBe(2)
    expect(tokenOffset(formula!, 3, 'end')).toBe(7)
    expect(tokenOffset(plain!, 1, 'end')).toBe(8)
  })
})

describe('filterStructTypeTree', () => {
  it('keeps ancestors of matches and whole subtrees of matching nodes', () => {
    const roots = buildStructTypeTree(TYPES)
    // T5 在 代数(1) > 函数(4) 之下:命中时祖先保留,兄弟分支(几何、设问)被滤掉
    const filtered = filterStructTypeTree(roots, 't5')
    expect(flattenStructTypeTree(filtered).map(n => n.id)).toEqual([1, 4, 5])
    // 命中「函数」:其子类型原样保留
    expect(flattenStructTypeTree(filterStructTypeTree(roots, 'T4')).map(n => n.id)).toEqual([1, 4, 5])
    expect(filterStructTypeTree(roots, '  ')).toBe(roots)
    expect(filterStructTypeTree(roots, 'nothing')).toEqual([])
  })
})
