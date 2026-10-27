export const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--primary)',
]

export const chartColor = (i: number): string => CHART_COLORS[i % CHART_COLORS.length]!

export const QUESTION_TYPE_LABEL_KEYS: Record<string, string> = {
  single_choice: 'questions.types.singleChoice',
  multiple_choice: 'questions.types.multipleChoice',
  true_false: 'questions.types.trueFalse',
  fill_in_the_blank: 'questions.types.fillInTheBlank',
  free_response: 'questions.types.freeResponse',
  option_matching: 'questions.types.optionMatching',
}

export const STATUS_COLORS: Record<string, string> = {
  draft: 'var(--muted-foreground)',
  pending: 'var(--chart-4)',
  published: 'var(--chart-2)',
  archived: 'var(--chart-3)',
}

const escapeHtml = (s: string): string =>
  s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

export interface TooltipRow {
  color: string
  label: string
  value: string
}

/** unovis 的 tooltip/crosshair 只接受 HTML 字符串;样式与 ChartTooltipContent 保持一致。 */
export function tooltipHtml(title: string | null, rows: TooltipRow[]): string {
  const head = title ? `<div class="font-medium">${escapeHtml(title)}</div>` : ''
  const body = rows
    .map(r => `<div class="flex items-center gap-2"><span class="size-2.5 shrink-0 rounded-[2px]" style="background:${r.color}"></span><span class="text-muted-foreground">${escapeHtml(r.label)}</span><span class="ml-auto pl-3 font-mono font-medium tabular-nums text-foreground">${escapeHtml(r.value)}</span></div>`)
    .join('')
  return `<div class="border-border/50 bg-background grid min-w-[8rem] gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs shadow-xl">${head}<div class="grid gap-1.5">${body}</div></div>`
}
