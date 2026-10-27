import { describe, expect, it } from 'vitest'
import { chartColor, CHART_COLORS, tooltipHtml } from '../dashboard'

describe('dashboard helpers', () => {
  it('cycles chart colors', () => {
    expect(chartColor(0)).toBe(CHART_COLORS[0])
    expect(chartColor(CHART_COLORS.length)).toBe(CHART_COLORS[0])
  })

  it('escapes user-provided text in tooltips', () => {
    const html = tooltipHtml('<b>t</b>', [{ color: 'red', label: 'a&"b', value: '1' }])
    expect(html).toContain('&lt;b&gt;t&lt;/b&gt;')
    expect(html).toContain('a&amp;&quot;b')
    expect(html).not.toContain('<b>t</b>')
  })

  it('omits the title row when title is null', () => {
    expect(tooltipHtml(null, [])).not.toContain('font-medium')
  })
})
