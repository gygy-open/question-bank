import { z } from 'zod'

type Translate = (key: string, params?: Record<string, unknown>) => string

/**
 * 全局 zod 错误文案：仅覆盖未显式传入 message 的常见校验，其余沿用 zod 默认文案。
 * t 在校验时才调用，因此切换语言后新的校验结果会使用新语言。
 */
export function createZodErrorMap(t: Translate): z.ZodErrorMap {
  return (issue, ctx) => {
    switch (issue.code) {
      case z.ZodIssueCode.invalid_type:
        if (issue.received === 'undefined' || issue.received === 'null') {
          return { message: t('validation.required') }
        }
        break
      case z.ZodIssueCode.too_small: {
        const min = Number(issue.minimum)
        if (issue.type === 'string') {
          return { message: min <= 1 ? t('validation.required') : t('validation.minLength', { min }) }
        }
        if (issue.type === 'number') return { message: t('validation.min', { min }) }
        if (issue.type === 'array' || issue.type === 'set') return { message: t('validation.minItems', { min }) }
        break
      }
      case z.ZodIssueCode.too_big: {
        const max = Number(issue.maximum)
        if (issue.type === 'string') return { message: t('validation.maxLength', { max }) }
        if (issue.type === 'number') return { message: t('validation.max', { max }) }
        if (issue.type === 'array' || issue.type === 'set') return { message: t('validation.maxItems', { max }) }
        break
      }
      case z.ZodIssueCode.invalid_string:
        if (issue.validation === 'email') return { message: t('validation.email') }
        if (issue.validation === 'url') return { message: t('validation.url') }
        break
    }
    return { message: ctx.defaultError }
  }
}
