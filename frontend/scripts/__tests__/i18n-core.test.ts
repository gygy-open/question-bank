import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  apply,
  check,
  outFile,
  pendingFile,
  placeholdersOf,
  resolvePaths,
  sync,
  syntaxIssue,
  validateTranslation,
  type I18nPaths,
} from '../i18n-core.mts'

let paths: I18nPaths

const write = (file: string, data: unknown) => writeFileSync(file, JSON.stringify(data, null, 2) + '\n')
const read = (file: string) => JSON.parse(readFileSync(file, 'utf8'))
const writeLocale = (locale: string, data: unknown) => write(join(paths.localesDir, `${locale}.json`), data)
const readLocale = (locale: string) => read(join(paths.localesDir, `${locale}.json`))

beforeEach(() => {
  paths = resolvePaths(mkdtempSync(join(tmpdir(), 'i18n-')))
  mkdirSync(paths.localesDir)
})

afterEach(() => {
  rmSync(paths.root, { recursive: true, force: true })
})

describe('message helpers', () => {
  it('extracts placeholders, ignoring literal interpolations', () => {
    expect(placeholdersOf("当前 v{current}，共 {count} 项 {'@'}")).toEqual(['count', 'current'])
  })

  it('detects vue-i18n syntax problems', () => {
    expect(syntaxIssue('a@b.com')).toMatch(/unescaped/)
    expect(syntaxIssue("a{'@'}b.com")).toBeNull()
    expect(syntaxIssue('one | two')).toMatch(/unescaped/)
    expect(syntaxIssue('broken {')).toMatch(/unbalanced/)
    expect(syntaxIssue('ok {name}')).toBeNull()
  })

  it('validates translations', () => {
    expect(validateTranslation('en-US', '共 {n} 项', '{n} items')).toBeNull()
    expect(validateTranslation('en-US', '共 {n} 项', '{count} items')).toMatch(/placeholders/)
    expect(validateTranslation('en-US', '题库', '题库')).toMatch(/Chinese/)
    expect(validateTranslation('en-US', '题库', '')).toMatch(/empty/)
    expect(validateTranslation('en-US', '题库', 42)).toMatch(/empty/)
    expect(validateTranslation('ja-JP', '题库', '問題集')).toBeNull()
  })
})

describe('sync / apply / check', () => {
  it('reorders, prunes, exports missing and stale entries, and keeps stale text until re-translated', () => {
    writeLocale('zh-CN', { a: { x: '甲', y: '乙 {n}' }, b: '丙' })
    writeLocale('en-US', { extra: 'Extra', b: 'C', a: { x: 'A' } })

    const [first] = sync(paths)
    expect(first).toMatchObject({ locale: 'en-US', missing: ['a.y'], stale: [], removed: ['extra'] })
    expect(Object.keys(readLocale('en-US'))).toEqual(['a', 'b'])
    expect(read(pendingFile(paths, 'en-US'))).toEqual({ 'a.y': '乙 {n}' })
    expect(check(paths)).toEqual([{ locale: 'en-US', key: 'a.y', problem: 'missing' }])

    write(outFile(paths, 'en-US'), { 'a.y': 'B {n}' })
    const [applied] = apply(paths)
    expect(applied).toMatchObject({ applied: ['a.y'], rejected: [], remaining: 0 })
    expect(readLocale('en-US')).toEqual({ a: { x: 'A', y: 'B {n}' }, b: 'C' })
    expect(existsSync(pendingFile(paths, 'en-US'))).toBe(false)
    expect(check(paths)).toEqual([])

    // 修改中文原文 -> 译文过期，但旧译文保留作兜底
    writeLocale('zh-CN', { a: { x: '甲（新）', y: '乙 {n}' }, b: '丙' })
    expect(check(paths)).toEqual([{ locale: 'en-US', key: 'a.x', problem: 'stale' }])
    const [second] = sync(paths)
    expect(second!.stale).toEqual(['a.x'])
    expect(readLocale('en-US').a.x).toBe('A')
    expect(read(pendingFile(paths, 'en-US'))).toEqual({ 'a.x': '甲（新）' })
  })

  it('rejects invalid translations and keeps them pending', () => {
    writeLocale('zh-CN', { a: '共 {n} 项', b: '好', c: '丙' })
    writeLocale('en-US', {})
    sync(paths)

    write(outFile(paths, 'en-US'), { a: '{count} items', b: 'OK', zzz: 'unknown' })
    const [r] = apply(paths)
    expect(r!.applied).toEqual(['b'])
    expect(r!.rejected.map(x => x.key)).toEqual(['a'])
    expect(r!.ignored).toEqual(['zzz'])
    expect(r!.remaining).toBe(2)
    expect(read(pendingFile(paths, 'en-US'))).toEqual({ a: '共 {n} 项', c: '丙' })
    expect(existsSync(outFile(paths, 'en-US'))).toBe(false)
    expect(readLocale('en-US')).toEqual({ b: 'OK' })
  })

  it('discards translations whose source changed after sync', () => {
    writeLocale('zh-CN', { a: '甲' })
    writeLocale('en-US', {})
    sync(paths)
    writeLocale('zh-CN', { a: '甲甲' })
    write(outFile(paths, 'en-US'), { a: 'A' })

    const [r] = apply(paths)
    expect(r!.applied).toEqual([])
    expect(r!.rejected[0]!.reason).toMatch(/source changed/)
    expect(readLocale('en-US')).toEqual({})
  })

  it('reports untracked, out-of-order and invalid entries', () => {
    writeLocale('zh-CN', { a: '甲', b: '乙 {n}' })
    writeLocale('en-US', { b: 'B', a: 'A' })
    const problems = check(paths).map(i => `${i.key}:${i.problem}`)
    expect(problems).toContain('a:not tracked in lock')
    expect(problems).toContain('b:placeholders mismatch: expected [n], got []')
    expect(problems).toContain('*:key order differs from base locale')
  })
})
