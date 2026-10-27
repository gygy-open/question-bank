/// <reference types="node" />
/**
 * i18n 翻译文件维护 CLI。
 *
 *   pnpm i18n:sync   以 zh-CN 为准重排/清理其他语言文件，导出缺失或过期条目到 i18n/.pending/<locale>.json
 *                    加 --split <n> 时再按顶层命名空间拆成 <locale>.part<k>.json，供多个翻译方并行处理
 *   pnpm i18n:apply  校验 i18n/.pending/<locale>.out.json（及 <locale>.part<k>.out.json）中的译文并合并，更新 lock
 *   pnpm i18n:check  只读校验（含硬编码中文检查），有问题时以非 0 退出（供 CI 使用）
 *   pnpm i18n:merge  把 i18n/.fragments/*.json（并行批次新增的 zh-CN key）合并进 zh-CN.json
 *   pnpm i18n:baseline  把 app/ 中现有的非注释中文行登记为有意保留的内容语言
 */
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { MergeConflictError, apply, check, mergeFragments, pendingFile, outFile, resolvePaths, sync } from './i18n-core.mts'
import { checkHardcoded, writeBaseline } from './i18n-hardcoded.mts'

const paths = resolvePaths(fileURLToPath(new URL('../i18n', import.meta.url)))
const frontendDir = fileURLToPath(new URL('..', import.meta.url))
const baselineFile = join(paths.root, '.hardcoded-baseline.json')
const rel = (p: string) => relative(process.cwd(), p)
const preview = (keys: string[], n = 10) =>
  keys.slice(0, n).join(', ') + (keys.length > n ? `, ... (+${keys.length - n})` : '')

function runSync(): number {
  const splitArg = process.argv.indexOf('--split')
  const split = splitArg > -1 ? Number(process.argv[splitArg + 1]) : 0
  if (splitArg > -1 && !(Number.isInteger(split) && split > 1)) {
    console.error('--split expects an integer >= 2')
    return 2
  }
  let pendingTotal = 0
  for (const r of sync(paths, { split })) {
    const count = r.missing.length + r.stale.length
    pendingTotal += count
    console.log(`[${r.locale}] missing ${r.missing.length}, stale ${r.stale.length}, removed ${r.removed.length}`)
    if (r.missing.length) console.log(`  missing: ${preview(r.missing)}`)
    if (r.stale.length) console.log(`  stale:   ${preview(r.stale)}`)
    if (r.removed.length) console.log(`  removed: ${preview(r.removed)}`)
    if (count) console.log(`  -> translate ${rel(pendingFile(paths, r.locale))} into ${rel(outFile(paths, r.locale))}, then run i18n:apply`)
    if (r.parts) console.log(`  -> or translate the ${r.parts} shard(s) i18n/.pending/${r.locale}.part<k>.json into ${r.locale}.part<k>.out.json in parallel`)
  }
  if (!pendingTotal) console.log('All locales are up to date.')
  return 0
}

function runApply(): number {
  const results = apply(paths)
  if (!results.length) {
    console.log('No *.out.json found in i18n/.pending; nothing to apply.')
    return 0
  }
  let failed = false
  for (const r of results) {
    console.log(`[${r.locale}] applied ${r.applied.length}, rejected ${r.rejected.length}, remaining ${r.remaining}`)
    for (const { key, reason } of r.rejected) console.log(`  rejected ${key}: ${reason}`)
    if (r.ignored.length) console.log(`  ignored unknown keys: ${preview(r.ignored)}`)
    if (r.rejected.length || r.remaining) failed = true
  }
  return failed ? 1 : 0
}

function runCheck(): number {
  const issues = check(paths)
  const hardcoded = checkHardcoded(frontendDir, baselineFile)
  if (!issues.length && !hardcoded.length) {
    console.log('i18n check passed.')
    return 0
  }
  for (const i of issues) console.log(`[${i.locale}] ${i.key}: ${i.problem}`)
  if (issues.length) console.log(`\n${issues.length} issue(s). Run "pnpm i18n:sync" and translate pending entries.`)
  for (const h of hardcoded) console.log(`${h.file}:${h.line}: ${h.text}`)
  if (hardcoded.length) {
    console.log(`\n${hardcoded.length} hardcoded Chinese line(s). Use t('...') for UI text; if it is content language, run "pnpm i18n:baseline".`)
  }
  return 1
}

function runBaseline(): number {
  const baseline = writeBaseline(frontendDir, baselineFile)
  const lines = Object.values(baseline).reduce((n, l) => n + l.length, 0)
  console.log(`Recorded ${lines} line(s) in ${Object.keys(baseline).length} file(s) to ${rel(baselineFile)}.`)
  return 0
}

function runMerge(): number {
  try {
    const results = mergeFragments(paths)
    if (!results.length) console.log('No fragments in i18n/.fragments; nothing to merge.')
    for (const r of results) {
      console.log(`[${r.fragment}] added ${r.added.length}, duplicates ${r.duplicates.length}`)
      if (r.duplicates.length) console.log(`  duplicates (ignored): ${preview(r.duplicates)}`)
    }
    return 0
  } catch (e) {
    if (!(e instanceof MergeConflictError)) throw e
    for (const c of e.conflicts) console.log(`[${c.fragment}] ${c.key}: ${c.reason}`)
    console.log(`\n${e.message}; nothing was written.`)
    return 1
  }
}

const commands: Record<string, () => number> = { sync: runSync, apply: runApply, check: runCheck, merge: runMerge, baseline: runBaseline }
const cmd = process.argv[2] ?? ''
if (!commands[cmd]) {
  console.error('Usage: node scripts/i18n.mts <sync|apply|check|merge|baseline>')
  process.exit(2)
}
process.exit(commands[cmd]!())
