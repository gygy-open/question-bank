import { describe, it, expect } from 'vitest'
import {
  DEFAULT_ANSWER_SPACE_RULES,
  clampAnswerSpaceLines,
  resolveAnswerSpaceProps,
  resolveAnswerSpacePropsOrFallback,
} from '@/lib/answerSpaceRules'

// 该文件与后端 tests/test_answer_space_rules.py 的纯函数用例一一对应，
// 两侧口径一旦漂移，编辑器预览就会与导出结果不一致。
describe('作答区规则解析', () => {
  it('选择题与判断题默认不配作答区', () => {
    expect(resolveAnswerSpaceProps('single_choice', 3)).toBeNull()
    expect(resolveAnswerSpaceProps('multiple_choice', 3)).toBeNull()
    expect(resolveAnswerSpaceProps('true_false', 2)).toBeNull()
  })

  it('解答题行数随分值增长并受上下限约束', () => {
    expect(resolveAnswerSpaceProps('free_response', null)).toEqual({ lines: 2, style: 'lined' })
    expect(resolveAnswerSpaceProps('free_response', 6)).toEqual({ lines: 5, style: 'lined' })
    expect(resolveAnswerSpaceProps('free_response', 60)).toEqual({ lines: 20, style: 'lined' })
    expect(resolveAnswerSpaceProps('free_response', 1)).toEqual({ lines: 2, style: 'lined' })
  })

  it('填空题比解答题短且用留白', () => {
    const fill = resolveAnswerSpaceProps('fill_in_the_blank', 4)
    const free = resolveAnswerSpaceProps('free_response', 4)
    expect(fill!.lines).toBeLessThan(free!.lines)
    expect(fill!.style).toBe('blank')
  })

  it('对选择题显式插入作答区时仍给出可用值', () => {
    expect(resolveAnswerSpacePropsOrFallback('single_choice', 3)).toEqual({ lines: 2, style: 'lined' })
    expect(resolveAnswerSpacePropsOrFallback(null, 10)).toEqual({ lines: 8, style: 'lined' })
  })

  it('学科覆盖生效，未覆盖题型保持默认', () => {
    const rules = {
      ...DEFAULT_ANSWER_SPACE_RULES,
      free_response: {
        ...DEFAULT_ANSWER_SPACE_RULES.free_response!,
        lines_per_score: 2,
        max_lines: 40,
      },
    }
    expect(resolveAnswerSpaceProps('free_response', 6, rules)).toEqual({ lines: 12, style: 'lined' })
    expect(resolveAnswerSpaceProps('single_choice', 6, rules)).toBeNull()
  })

  it('行数钳制到 1..50', () => {
    expect(clampAnswerSpaceLines(0)).toBe(1)
    expect(clampAnswerSpaceLines(-3)).toBe(1)
    expect(clampAnswerSpaceLines(999)).toBe(50)
    expect(clampAnswerSpaceLines(4.4)).toBe(4)
  })
})
