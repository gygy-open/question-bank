import { computed, ref, watch } from 'vue'
import { DEFAULT_ANSWER_SPACE_RULES } from '@/lib/answerSpaceRules'
import type { AnswerSpaceRules } from '@/lib/answerSpaceRules'

export interface AnswerSpaceRulesResponse {
  rules: AnswerSpaceRules
  defaults: AnswerSpaceRules
  is_custom: boolean
}

export function useAnswerSpaceRules() {
  const { $api } = useNuxtApp()
  const path = (subjectId: number) => `/subjects/${subjectId}/answer-space-rules`

  const getRules = (subjectId: number) => $api<AnswerSpaceRulesResponse>(path(subjectId))

  const saveRules = (subjectId: number, rules: AnswerSpaceRules) =>
    $api<AnswerSpaceRulesResponse>(path(subjectId), { method: 'PUT', body: { rules } })

  const resetRules = (subjectId: number) =>
    $api<AnswerSpaceRulesResponse>(path(subjectId), { method: 'DELETE' })

  return { getRules, saveRules, resetRules }
}

/** 跟随学科自动加载规则；加载失败或未指定学科时回退到代码默认值，不阻断编辑。 */
export function useSubjectAnswerSpaceRules(subjectId: () => number | null | undefined) {
  const { getRules } = useAnswerSpaceRules()
  const loaded = ref<AnswerSpaceRules | null>(null)

  watch(
    subjectId,
    async (id) => {
      if (!id) {
        loaded.value = null
        return
      }
      try {
        loaded.value = (await getRules(id)).rules
      } catch {
        loaded.value = null
      }
    },
    { immediate: true },
  )

  return computed(() => loaded.value ?? DEFAULT_ANSWER_SPACE_RULES)
}
