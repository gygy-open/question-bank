/// <reference types="node" />
/**
 * i18n 翻译文件维护的核心逻辑（纯函数 + 文件读写），CLI 见 ./i18n.mts。
 *
 * 约定：
 * - i18n/locales/zh-CN.json 是唯一事实来源，其余 locale 的 key 集合与顺序完全由它决定。
 * - i18n/.translation-lock.json 记录每条译文翻译时所依据的中文原文哈希；原文变化即判定译文过期。
 * - i18n/.pending/<locale>.json 是待翻译条目（扁平 key → 中文），<locale>.out.json 由翻译方写入。
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

export const BASE_LOCALE = 'zh-CN'

type Messages = { [key: string]: string | Messages }
type Flat = Map<string, string>
type Lock = Record<string, Record<string, string>>

export interface I18nPaths {
  root: string
  localesDir: string
  lockFile: string
  pendingDir: string
  fragmentsDir: string
}

export function resolvePaths(root: string): I18nPaths {
  return {
    root,
    localesDir: join(root, 'locales'),
    lockFile: join(root, '.translation-lock.json'),
    pendingDir: join(root, '.pending'),
    fragmentsDir: join(root, '.fragments'),
  }
}

// ---------- 纯函数 ----------

export function hashSource(text: string): string {
  return createHash('sha1').update(text).digest('hex').slice(0, 12)
}

export function flatten(obj: Messages, prefix = '', out: Flat = new Map()): Flat {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'string') out.set(key, v)
    else if (v && typeof v === 'object') flatten(v, key, out)
    else throw new Error(`Invalid message value at "${key}": expected string or object`)
  }
  return out
}

export function unflatten(flat: Flat): Messages {
  const root: Messages = {}
  for (const [key, value] of flat) {
    const parts = key.split('.')
    let node = root
    for (const part of parts.slice(0, -1)) {
      if (typeof node[part] === 'string') throw new Error(`Key conflict at "${key}"`)
      node = (node[part] ??= {}) as Messages
    }
    node[parts.at(-1)!] = value
  }
  return root
}

// vue-i18n 字面量插值 {'@'}，既不算占位符也不算特殊字符
const LITERAL_RE = /\{'[^']*'\}/g
const PLACEHOLDER_RE = /\{\s*(\w+)\s*\}/g

export function placeholdersOf(message: string): string[] {
  const stripped = message.replace(LITERAL_RE, '')
  return [...new Set([...stripped.matchAll(PLACEHOLDER_RE)].map(m => m[1]!))].sort()
}

/** 返回消息中的 vue-i18n 语法问题，无问题返回 null。 */
export function syntaxIssue(message: string): string | null {
  const stripped = message.replace(LITERAL_RE, '').replace(PLACEHOLDER_RE, '')
  if (/[@|]/.test(stripped)) return `unescaped "@" or "|" (write {'@'} / {'|'})`
  if (/[{}]/.test(stripped)) return 'unbalanced or invalid "{ }"'
  return null
}

const HAN_RE = /\p{Script=Han}/u

function usesHan(locale: string): boolean {
  return /^(zh|ja)\b/i.test(locale)
}

/** 校验一条译文；合格返回 null，否则返回原因。 */
export function validateTranslation(locale: string, source: string, translated: unknown): string | null {
  if (typeof translated !== 'string' || !translated.trim()) return 'empty or not a string'
  const issue = syntaxIssue(translated)
  if (issue) return issue
  const expected = placeholdersOf(source)
  const actual = placeholdersOf(translated)
  if (expected.join(',') !== actual.join(',')) {
    return `placeholders mismatch: expected [${expected.join(', ')}], got [${actual.join(', ')}]`
  }
  if (!usesHan(locale) && HAN_RE.test(translated)) return 'contains untranslated Chinese characters'
  return null
}

export type EntryStatus = 'ok' | 'missing' | 'stale'

export function entryStatus(source: string, translated: string | undefined, lockHash: string | undefined): EntryStatus {
  if (translated === undefined) return 'missing'
  if (lockHash !== undefined && lockHash !== hashSource(source)) return 'stale'
  return 'ok'
}

// ---------- 文件读写 ----------

function readJson<T>(file: string, fallback: T): T {
  if (!existsSync(file)) return fallback
  return JSON.parse(readFileSync(file, 'utf8')) as T
}

function writeJson(file: string, data: unknown): void {
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`)
}

export function listTargetLocales(paths: I18nPaths): string[] {
  return readdirSync(paths.localesDir)
    .filter(f => f.endsWith('.json'))
    .map(f => f.slice(0, -'.json'.length))
    .filter(l => l !== BASE_LOCALE)
    .sort()
}

function loadLocale(paths: I18nPaths, locale: string): Flat {
  return flatten(readJson<Messages>(join(paths.localesDir, `${locale}.json`), {}))
}

function saveLocale(paths: I18nPaths, locale: string, flat: Flat): void {
  writeJson(join(paths.localesDir, `${locale}.json`), unflatten(flat))
}

/** 按基准语言的 key 顺序挑出 target 中存在的条目。 */
function orderLike(base: Flat, target: Flat): Flat {
  const ordered: Flat = new Map()
  for (const key of base.keys()) {
    const v = target.get(key)
    if (v !== undefined) ordered.set(key, v)
  }
  return ordered
}

function loadLock(paths: I18nPaths): Lock {
  return readJson<Lock>(paths.lockFile, {})
}

function saveLock(paths: I18nPaths, lock: Lock, base: Flat): void {
  const sorted: Lock = {}
  for (const locale of Object.keys(lock).sort()) {
    const entries: Record<string, string> = {}
    for (const key of base.keys()) {
      const h = lock[locale]![key]
      if (h !== undefined) entries[key] = h
    }
    sorted[locale] = entries
  }
  writeJson(paths.lockFile, sorted)
}

export function pendingFile(paths: I18nPaths, locale: string): string {
  return join(paths.pendingDir, `${locale}.json`)
}

export function outFile(paths: I18nPaths, locale: string): string {
  return join(paths.pendingDir, `${locale}.out.json`)
}

export function partFile(paths: I18nPaths, locale: string, n: number, out = false): string {
  return join(paths.pendingDir, `${locale}.part${n}${out ? '.out' : ''}.json`)
}

/** 目录里属于某语言的分片文件（待翻译或译文）。 */
function listPartFiles(paths: I18nPaths, locale: string, out: boolean): string[] {
  if (!existsSync(paths.pendingDir)) return []
  const re = new RegExp(`^${locale.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.part(\\d+)${out ? '\\.out' : ''}\\.json$`)
  return readdirSync(paths.pendingDir)
    .filter(f => re.test(f))
    .sort((a, b) => Number(re.exec(a)![1]) - Number(re.exec(b)![1]))
    .map(f => join(paths.pendingDir, f))
}

/**
 * 把待翻译条目按顶层命名空间拆成最多 n 份（先放最大的组，每次放进最小的一份），
 * 同一命名空间的条目不会被拆开，方便翻译方保持措辞一致。
 */
export function splitByNamespace(entries: Record<string, string>, n: number): Record<string, string>[] {
  const groups = new Map<string, Record<string, string>>()
  for (const [key, value] of Object.entries(entries)) {
    const ns = key.split('.')[0]!
    if (!groups.has(ns)) groups.set(ns, {})
    groups.get(ns)![key] = value
  }
  const bins: Record<string, string>[] = Array.from({ length: Math.max(1, Math.min(n, groups.size)) }, () => ({}))
  const size = (b: Record<string, string>) => Object.keys(b).length
  for (const group of [...groups.values()].sort((a, b) => size(b) - size(a))) {
    const smallest = bins.reduce((m, b) => (size(b) < size(m) ? b : m))
    Object.assign(smallest, group)
  }
  return bins.filter(b => size(b) > 0)
}

function writePending(paths: I18nPaths, locale: string, entries: Record<string, string>, split = 0): void {
  for (const f of [...listPartFiles(paths, locale, false), ...listPartFiles(paths, locale, true)]) rmSync(f, { force: true })
  if (Object.keys(entries).length === 0) {
    rmSync(pendingFile(paths, locale), { force: true })
    return
  }
  mkdirSync(paths.pendingDir, { recursive: true })
  writeJson(pendingFile(paths, locale), entries)
  if (split > 1) {
    splitByNamespace(entries, split).forEach((part, i) => writeJson(partFile(paths, locale, i + 1), part))
  }
}

// ---------- 命令 ----------

export interface SyncResult {
  locale: string
  missing: string[]
  stale: string[]
  removed: string[]
  parts: number
}

/**
 * 以基准语言为准重建所有目标语言文件（顺序、删除多余 key），并把缺失/过期条目导出到 .pending。
 * 过期译文暂时保留在文件中，重译前仍可作为兜底显示。
 */
export function sync(paths: I18nPaths, options: { split?: number } = {}): SyncResult[] {
  const base = loadLocale(paths, BASE_LOCALE)
  saveLocale(paths, BASE_LOCALE, base)
  const lock = loadLock(paths)
  const results: SyncResult[] = []

  for (const locale of listTargetLocales(paths)) {
    const target = loadLocale(paths, locale)
    const localeLock = (lock[locale] ??= {})
    const pending: Record<string, string> = {}
    const result: SyncResult = { locale, missing: [], stale: [], removed: [], parts: 0 }

    for (const [key, source] of base) {
      const status = entryStatus(source, target.get(key), localeLock[key])
      if (status === 'ok') {
        // 尚未纳入 lock 的已有译文（如手工添加）视为对应当前原文
        localeLock[key] = hashSource(source)
      } else {
        pending[key] = source
        result[status].push(key)
      }
    }
    result.removed = [...target.keys()].filter(k => !base.has(k))

    saveLocale(paths, locale, orderLike(base, target))
    writePending(paths, locale, pending, options.split)
    result.parts = listPartFiles(paths, locale, false).length
    results.push(result)
  }

  saveLock(paths, lock, base)
  return results
}

export interface ApplyResult {
  locale: string
  applied: string[]
  rejected: { key: string; reason: string }[]
  ignored: string[]
  remaining: number
}

/** 校验 .pending/<locale>.out.json 中的译文，合格者按基准顺序合并并更新 lock。 */
export function apply(paths: I18nPaths): ApplyResult[] {
  const base = loadLocale(paths, BASE_LOCALE)
  const lock = loadLock(paths)
  const results: ApplyResult[] = []

  for (const locale of listTargetLocales(paths)) {
    const outPath = outFile(paths, locale)
    const outFiles = [outPath, ...listPartFiles(paths, locale, true)].filter(f => existsSync(f))
    if (!outFiles.length) continue

    const pending = readJson<Record<string, string>>(pendingFile(paths, locale), {})
    const out: Record<string, unknown> = {}
    for (const f of outFiles) Object.assign(out, readJson<Record<string, unknown>>(f, {}))
    const target = loadLocale(paths, locale)
    const localeLock = (lock[locale] ??= {})
    const result: ApplyResult = { locale, applied: [], rejected: [], ignored: [], remaining: 0 }
    const stillPending: Record<string, string> = {}

    for (const [key, source] of Object.entries(pending)) {
      if (base.get(key) !== source) {
        // 原文在 sync 之后又改了：丢弃，由下一次 sync 重新导出
        result.rejected.push({ key, reason: 'source changed since sync; run sync again' })
        continue
      }
      if (!(key in out)) {
        stillPending[key] = source
        continue
      }
      const reason = validateTranslation(locale, source, out[key])
      if (reason) {
        result.rejected.push({ key, reason })
        stillPending[key] = source
        continue
      }
      target.set(key, out[key] as string)
      localeLock[key] = hashSource(source)
      result.applied.push(key)
    }
    result.ignored = Object.keys(out).filter(k => !(k in pending))

    saveLocale(paths, locale, orderLike(base, target))
    writePending(paths, locale, stillPending)
    for (const f of outFiles) rmSync(f, { force: true })
    result.remaining = Object.keys(stillPending).length
    results.push(result)
  }

  saveLock(paths, lock, base)
  return results
}

export interface MergeResult {
  fragment: string
  added: string[]
  duplicates: string[]
}

export class MergeConflictError extends Error {
  conflicts: { fragment: string; key: string; reason: string }[]

  constructor(conflicts: { fragment: string; key: string; reason: string }[]) {
    super(`${conflicts.length} conflict(s) while merging fragments`)
    this.conflicts = conflicts
  }
}

/**
 * 把 .fragments/*.json（并行批次各自新增的基准语言 key）合并进基准语言文件，追加在末尾。
 * 与已有 key 值完全相同的视为重复并忽略；值不同或叶子/分组冲突则整体中止，不写任何文件。
 * 成功后删除已合并的片段文件。
 */
export function mergeFragments(paths: I18nPaths): MergeResult[] {
  if (!existsSync(paths.fragmentsDir)) return []
  const files = readdirSync(paths.fragmentsDir).filter(f => f.endsWith('.json')).sort()
  const base = loadLocale(paths, BASE_LOCALE)
  const results: MergeResult[] = []
  const conflicts: { fragment: string; key: string; reason: string }[] = []
  const origin = new Map<string, string>()

  for (const file of files) {
    const fragment = flatten(readJson<Messages>(join(paths.fragmentsDir, file), {}))
    const result: MergeResult = { fragment: file, added: [], duplicates: [] }
    for (const [key, value] of fragment) {
      const existing = base.get(key)
      if (existing !== undefined) {
        if (existing === value) result.duplicates.push(key)
        else conflicts.push({ fragment: file, key, reason: `already defined${origin.has(key) ? ` by ${origin.get(key)}` : ''} with a different value` })
        continue
      }
      const clash = [...base.keys()].find(k => k.startsWith(`${key}.`) || key.startsWith(`${k}.`))
      if (clash) {
        conflicts.push({ fragment: file, key, reason: `leaf/group clash with "${clash}"` })
        continue
      }
      const issue = syntaxIssue(value)
      if (issue) {
        conflicts.push({ fragment: file, key, reason: issue })
        continue
      }
      base.set(key, value)
      origin.set(key, file)
      result.added.push(key)
    }
    results.push(result)
  }

  if (conflicts.length) throw new MergeConflictError(conflicts)
  // 用 unflatten 重新分组：新增 key 落到同名命名空间下（如 common.*），新命名空间追加在末尾
  saveLocale(paths, BASE_LOCALE, base)
  for (const file of files) rmSync(join(paths.fragmentsDir, file))
  return results
}

export interface CheckIssue {
  locale: string
  key: string
  problem: string
}

/** 只读校验：key 集合与顺序、缺失/过期、lock 覆盖、占位符与语法。 */
export function check(paths: I18nPaths): CheckIssue[] {
  const issues: CheckIssue[] = []
  const base = loadLocale(paths, BASE_LOCALE)
  const lock = loadLock(paths)

  for (const [key, source] of base) {
    const issue = syntaxIssue(source)
    if (issue) issues.push({ locale: BASE_LOCALE, key, problem: issue })
  }

  for (const locale of listTargetLocales(paths)) {
    const target = loadLocale(paths, locale)
    const localeLock = lock[locale] ?? {}

    for (const [key, source] of base) {
      const translated = target.get(key)
      const status = entryStatus(source, translated, localeLock[key])
      if (status !== 'ok') {
        issues.push({ locale, key, problem: status })
        continue
      }
      if (localeLock[key] === undefined) issues.push({ locale, key, problem: 'not tracked in lock' })
      const reason = validateTranslation(locale, source, translated)
      if (reason) issues.push({ locale, key, problem: reason })
    }
    for (const key of target.keys()) {
      if (!base.has(key)) issues.push({ locale, key, problem: 'extra key not in base locale' })
    }
    const expectedOrder = [...orderLike(base, target).keys()].join('\n')
    const actualOrder = [...target.keys()].filter(k => base.has(k)).join('\n')
    if (expectedOrder !== actualOrder) issues.push({ locale, key: '*', problem: 'key order differs from base locale' })
  }
  return issues
}
