import type { Component } from 'vue'
import {
  Atom,
  Code,
  Dna,
  Dumbbell,
  FlaskConical,
  Globe,
  Landmark,
  Languages,
  BookOpenText,
  Music,
  Palette,
  ScrollText,
  Sigma,
} from '@lucide/vue'

// Cycle a fixed palette by subject id so each subject keeps a stable color.
const SUBJECT_COLORS = [
  'bg-red-500', 'bg-orange-500', 'bg-amber-500', 'bg-lime-500',
  'bg-emerald-500', 'bg-teal-500', 'bg-cyan-500', 'bg-blue-500',
  'bg-indigo-500', 'bg-violet-500', 'bg-fuchsia-500', 'bg-pink-500',
]

// Order matters: first match wins. Patterns cover Chinese and English names.
const SUBJECT_ICONS: Array<[RegExp, Component]> = [
  [/数学|math|算术|代数|几何|calculus|algebra|geometry|statistic|统计/i, Sigma],
  [/物理|physic/i, Atom],
  [/化学|chem/i, FlaskConical],
  [/生物|biolog|生命科学/i, Dna],
  [/英语|外语|日语|法语|德语|俄语|韩语|english|language|french|german|japanese|spanish/i, Languages],
  [/语文|文学|国学|literature|chinese|reading|writing/i, BookOpenText],
  [/历史|histor/i, ScrollText],
  [/地理|geograph/i, Globe],
  [/政治|道德|法治|法律|politic|civic|law\b|ethic/i, Landmark],
  [/信息|计算机|编程|程序|computer|informatic|program|coding|\bcs\b/i, Code],
  [/音乐|music/i, Music],
  [/美术|艺术|绘画|\bart\b|design/i, Palette],
  [/体育|健康|sport|physical education|\bpe\b/i, Dumbbell],
]

export const getSubjectColor = (id: number): string =>
  SUBJECT_COLORS[id % SUBJECT_COLORS.length] as string

export const getSubjectIcon = (name: string): Component | null =>
  SUBJECT_ICONS.find(([pattern]) => pattern.test(name))?.[1] ?? null

// Fallback label: initials of the first two Latin words ("HM"), or the first character (e.g. CJK).
export const getSubjectInitial = (name: string): string => {
  const trimmed = name.trim()
  const words = trimmed.split(/[\s_-]+/).filter(Boolean)
  const isLatin = /^[A-Za-z]/.test(trimmed)
  if (isLatin && words.length > 1) {
    return words.slice(0, 2).map((w) => w.charAt(0)).join('').toUpperCase()
  }
  return Array.from(trimmed)[0]?.toUpperCase() ?? '?'
}
