<script setup lang="ts">
import { computed } from 'vue'
import type { AnswerSpec, OptionSpec } from '@/types'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { matchingAnswerEntries, optionLabelsForAnswer } from '@/lib/answerFormat'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'

const props = defineProps<{
    answer: AnswerSpec | null | undefined
    options?: OptionSpec[] | null
    emptyText?: string
    /** 稿件内按空位的题号（blankId → 题号），缺省按空位序号。 */
    slotNumbers?: Record<string, string | undefined>
}>()

const choiceLabels = computed(() => optionLabelsForAnswer(props.answer, props.options))
const matchingEntries = computed(() => matchingAnswerEntries(props.answer, props.options, props.slotNumbers))
</script>

<template>
    <div class="text-sm">
        <template v-if="!answer">
            <span class="text-muted-foreground">{{ emptyText || '未填写' }}</span>
        </template>

        <!-- 单选 / 多选：展示 label，附带选项富文本 -->
        <template v-else-if="answer.kind === 'single_choice' || answer.kind === 'multiple_choice'">
            <span v-if="choiceLabels.length === 0" class="text-muted-foreground">{{ emptyText || '未填写' }}</span>
            <span v-else class="font-semibold text-foreground">{{ choiceLabels.join('、') }}</span>
        </template>

        <!-- 判断题 -->
        <template v-else-if="answer.kind === 'true_false'">
            <span class="font-semibold text-foreground">{{ answer.correct ? '正确' : '错误' }}</span>
        </template>

        <!-- 填空题 -->
        <template v-else-if="answer.kind === 'fill_in_the_blank'">
            <div class="flex flex-col gap-2">
                <div v-for="(blank, bIdx) in answer.blanks" :key="blank.id" class="flex items-start gap-2">
                    <span v-if="answer.blanks.length > 1" class="font-mono text-muted-foreground shrink-0 mt-1">{{ bIdx + 1 }}.</span>
                    <div class="flex flex-wrap items-center gap-1.5">
                        <template v-for="(acc, aIdx) in blank.accept" :key="aIdx">
                            <span v-if="!isEmptyRichDoc(acc)" class="rounded border bg-background px-2 py-0.5 [&_.prose]:my-0 [&_.prose>p]:my-0 [&_.prose]:text-xs">
                                <RichContent :content="acc" />
                            </span>
                            <span v-if="aIdx < blank.accept.length - 1 && !isEmptyRichDoc(blank.accept[aIdx + 1])" class="text-xs text-muted-foreground">或</span>
                        </template>
                    </div>
                </div>
            </div>
        </template>

        <!-- 解答题 -->
        <template v-else-if="answer.kind === 'free_response'">
            <RichContent :content="answer.reference" :empty-text="emptyText || '未填写'" class="[&_.prose]:my-0" />
        </template>

        <!-- 选项匹配 -->
        <template v-else-if="answer.kind === 'option_matching'">
            <span v-if="matchingEntries.length === 0" class="text-muted-foreground">{{ emptyText || '未填写' }}</span>
            <span v-else class="flex flex-wrap gap-x-3 gap-y-1">
                <span v-for="(entry, i) in matchingEntries" :key="i">
                    <span class="font-mono text-muted-foreground">{{ entry.number }}.</span>
                    <span class="ml-1 font-semibold text-foreground">{{ entry.label || '？' }}</span>
                </span>
            </span>
        </template>

        <!-- 旧格式未解析：只读展示原文 -->
        <template v-else-if="answer.kind === 'legacy_unresolved'">
            <div class="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/20">
                <div class="mb-1 text-xs font-medium text-amber-700 dark:text-amber-400">旧格式答案（未解析）</div>
                <RichContent :content="answer.raw" empty-text="（无内容）" class="[&_.prose]:my-0" />
            </div>
        </template>
    </div>
</template>
