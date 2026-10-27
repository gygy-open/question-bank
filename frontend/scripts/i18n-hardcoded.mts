/// <reference types="node" />
/**
 * 硬编码中文防回退：扫描 app/ 下 .vue/.ts 源码中的非注释中文行，与已登记的基线（有意保留的内容语言）比对。
 * 基线按「文件 → 去首尾空白后的整行文本」记录，与行号无关；同一行出现多次按次数计。
 */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

export type Baseline = Record<string, string[]>

export interface HardcodedLine {
  file: string
  line: number
  text: string
}

const HAN_RE = /\p{Script=Han}/u
const SOURCE_RE = /\.(vue|ts)$/
const TEST_RE = /(^|\/)__tests__\/|\.(test|spec)\.ts$/

const keepNewlines = (s: string) => s.replace(/[^\n]/g, '')

/** 去掉注释，保留换行以维持行号。启发式实现：只认行首的块注释和前面不是 `:` 的 `//`（避开 URL）。 */
export function stripComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, keepNewlines)
    .replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, keepNewlines)
    .split('\n')
    .map(line => line.replace(/(\s)\/\*.*?\*\//g, '$1').replace(/(^|[^:'"`\\])\/\/.*$/, '$1'))
    .join('\n')
}

export function findHardcoded(source: string): { line: number; text: string }[] {
  return stripComments(source)
    .split('\n')
    .flatMap((text, i) => (HAN_RE.test(text) ? [{ line: i + 1, text: text.trim() }] : []))
}

function listSources(dir: string, root: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    const rel = relative(root, full).split(sep).join('/')
    if (entry.isDirectory()) listSources(full, root, out)
    else if (SOURCE_RE.test(entry.name) && !TEST_RE.test(rel)) out.push(rel)
  }
  return out
}

/** 扫描 frontendDir/app，返回「相对 frontendDir 的路径 → 中文行」。 */
export function scanHardcoded(frontendDir: string): Map<string, { line: number; text: string }[]> {
  const result = new Map<string, { line: number; text: string }[]>()
  for (const file of listSources(join(frontendDir, 'app'), frontendDir).sort()) {
    const found = findHardcoded(readFileSync(join(frontendDir, file), 'utf8'))
    if (found.length) result.set(file, found)
  }
  return result
}

export function buildBaseline(frontendDir: string): Baseline {
  const baseline: Baseline = {}
  for (const [file, lines] of scanHardcoded(frontendDir)) baseline[file] = lines.map(l => l.text).sort()
  return baseline
}

export function writeBaseline(frontendDir: string, baselineFile: string): Baseline {
  const baseline = buildBaseline(frontendDir)
  writeFileSync(baselineFile, `${JSON.stringify(baseline, null, 2)}\n`)
  return baseline
}

/** 返回基线之外新增的中文行。 */
export function checkHardcoded(frontendDir: string, baselineFile: string): HardcodedLine[] {
  const baseline: Baseline = existsSync(baselineFile) ? JSON.parse(readFileSync(baselineFile, 'utf8')) : {}
  const issues: HardcodedLine[] = []
  for (const [file, lines] of scanHardcoded(frontendDir)) {
    const allowed = new Map<string, number>()
    for (const text of baseline[file] ?? []) allowed.set(text, (allowed.get(text) ?? 0) + 1)
    for (const { line, text } of lines) {
      const left = allowed.get(text) ?? 0
      if (left > 0) allowed.set(text, left - 1)
      else issues.push({ file, line, text })
    }
  }
  return issues
}
