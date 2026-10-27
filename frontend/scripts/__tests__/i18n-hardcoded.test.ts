import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { checkHardcoded, findHardcoded, writeBaseline } from '../i18n-hardcoded.mts'

describe('findHardcoded', () => {
  it('ignores comments but keeps line numbers', () => {
    const source = [
      '<!-- 模板注释 -->',
      '/**',
      ' * 文档注释',
      ' */',
      "const a = 1 // 行尾注释",
      "const b = /* 行内注释 */ 2",
      "const url = 'https://例子.com'",
      "const label = '题目'",
      '<p>正文</p>',
    ].join('\n')
    expect(findHardcoded(source)).toEqual([
      { line: 7, text: "const url = 'https://例子.com'" },
      { line: 8, text: "const label = '题目'" },
      { line: 9, text: '<p>正文</p>' },
    ])
  })

  it('does not treat accept="image/*" as a comment start', () => {
    expect(findHardcoded('<input accept="image/*" />\n<p>上传</p>\n<!-- */ -->')).toEqual([
      { line: 2, text: '<p>上传</p>' },
    ])
  })
})

describe('checkHardcoded', () => {
  let root: string
  const write = (file: string, content: string) => writeFileSync(join(root, file), content)

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'i18n-hardcoded-'))
    mkdirSync(join(root, 'app/__tests__'), { recursive: true })
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it('reports only lines beyond the baseline, counting duplicates', () => {
    const baselineFile = join(root, 'baseline.json')
    write('app/a.ts', "const x = '答案'\n")
    write('app/__tests__/a.test.ts', "const y = '测试'\n")
    expect(writeBaseline(root, baselineFile)).toEqual({ 'app/a.ts': ["const x = '答案'"] })
    expect(checkHardcoded(root, baselineFile)).toEqual([])

    write('app/a.ts', "const x = '答案'\nconst x = '答案'\nconst z = '新增'\n")
    expect(checkHardcoded(root, baselineFile)).toEqual([
      { file: 'app/a.ts', line: 2, text: "const x = '答案'" },
      { file: 'app/a.ts', line: 3, text: "const z = '新增'" },
    ])
  })
})
