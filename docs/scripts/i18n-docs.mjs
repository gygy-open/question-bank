#!/usr/bin/env node
// Docs translation tracker. zh-CN (docs root) is the single source of truth;
// translations live in docs/<locale>/ with the same relative paths.
//
//   node scripts/i18n-docs.mjs status          list missing / stale / orphan translations
//   node scripts/i18n-docs.mjs check           same, exit 1 on any problem (incl. structure)
//   node scripts/i18n-docs.mjs mark <file...>  record current zh source hash as translated
//   node scripts/i18n-docs.mjs mark --all      mark every existing translation
//
// <file> is a source-relative path such as `guide/introduction.md`, or
// `../README.md` for the repository README (see EXTRA).
// The lock file (.translation-lock.json) must be committed.

import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const LOCALES = ['en']
// specs/ and design/ are internal and not translated.
const SCOPE = ['index.md', 'guide', 'desktop', 'server', 'admin', 'features', 'development']
// Files outside docs/ that are translated side by side: source → locale → target (docs-relative).
// Only staleness is tracked for these; their content may intentionally differ per locale
// (e.g. the English README omits China-specific sections), so no structure check.
const EXTRA = { '../README.md': { en: '../README.en.md' } }
const LOCK_PATH = join(ROOT, '.translation-lock.json')

const sha = (text) => createHash('sha256').update(text).digest('hex').slice(0, 16)

function walk(rel) {
  const abs = join(ROOT, rel)
  if (!existsSync(abs)) return []
  if (statSync(abs).isFile()) return rel.endsWith('.md') ? [rel] : []
  return readdirSync(abs).flatMap((name) => walk(join(rel, name)))
}

const targetOf = (locale, file) => join(ROOT, EXTRA[file]?.[locale] ?? join(locale, file))

const sources = () =>
  [...SCOPE.flatMap(walk), ...Object.keys(EXTRA).filter((f) => existsSync(join(ROOT, f)))].sort()
const translations = (locale) =>
  [
    ...SCOPE.flatMap((p) => walk(join(locale, p)).map((f) => relative(locale, f))),
    ...Object.keys(EXTRA).filter((f) => EXTRA[f][locale] && existsSync(targetOf(locale, f)))
  ].sort()

const readLock = () => (existsSync(LOCK_PATH) ? JSON.parse(readFileSync(LOCK_PATH, 'utf8')) : {})
const writeLock = (lock) => writeFileSync(LOCK_PATH, JSON.stringify(lock, null, 2) + '\n')

// Markdown skeleton that must survive translation unchanged.
function skeleton(text) {
  const lines = text.split('\n')
  let fence = 0
  let containers = 0
  let headings = 0
  let inFence = false
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) {
      fence++
      inFence = !inFence
      continue
    }
    if (inFence) continue
    if (/^:::/.test(line)) containers++
    if (/^#{1,6}\s/.test(line)) headings++
  }
  const images = (text.match(/!\[[^\]]*\]\([^)]*\)/g) || []).length
  return { fence, containers, headings, images }
}

function collect() {
  const lock = readLock()
  const report = []
  for (const locale of LOCALES) {
    const src = sources()
    const tr = new Set(translations(locale))
    const missing = []
    const stale = []
    const structure = []
    for (const file of src) {
      if (!tr.has(file)) {
        missing.push(file)
        continue
      }
      const source = readFileSync(join(ROOT, file), 'utf8')
      if (lock[locale]?.[file] !== sha(source)) stale.push(file)
      if (EXTRA[file]) continue
      const a = skeleton(source)
      const b = skeleton(readFileSync(targetOf(locale, file), 'utf8'))
      const diff = Object.keys(a).filter((k) => a[k] !== b[k])
      if (diff.length) structure.push(`${file} (${diff.map((k) => `${k}: ${a[k]}→${b[k]}`).join(', ')})`)
    }
    const srcSet = new Set(src)
    const orphan = [...tr].filter((f) => !srcSet.has(f))
    report.push({ locale, missing, stale, orphan, structure })
  }
  return report
}

function printReport(report) {
  let problems = 0
  for (const { locale, ...groups } of report) {
    console.log(`[${locale}]`)
    for (const [name, files] of Object.entries(groups)) {
      problems += files.length
      console.log(`  ${name}: ${files.length}`)
      for (const f of files) console.log(`    - ${f}`)
    }
  }
  return problems
}

function mark(args) {
  const lock = readLock()
  const all = args.includes('--all')
  for (const locale of LOCALES) {
    const tr = new Set(translations(locale))
    const files = all ? sources().filter((f) => tr.has(f)) : args.filter((a) => !a.startsWith('--'))
    lock[locale] ??= {}
    for (const file of files) {
      if (!existsSync(join(ROOT, file))) throw new Error(`No source file: ${file}`)
      if (!tr.has(file)) throw new Error(`No ${locale} translation for: ${file}`)
      lock[locale][file] = sha(readFileSync(join(ROOT, file), 'utf8'))
      console.log(`marked ${locale}/${file}`)
    }
    // Drop entries whose source no longer exists.
    for (const file of Object.keys(lock[locale])) {
      if (!existsSync(join(ROOT, file))) delete lock[locale][file]
    }
    lock[locale] = Object.fromEntries(Object.entries(lock[locale]).sort())
  }
  writeLock(lock)
}

const [cmd = 'status', ...args] = process.argv.slice(2)
if (cmd === 'mark') mark(args)
else if (cmd === 'status') printReport(collect())
else if (cmd === 'check') process.exitCode = printReport(collect()) ? 1 : 0
else {
  console.error(`Unknown command: ${cmd}`)
  process.exitCode = 2
}
