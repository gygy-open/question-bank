<script setup lang="ts">
import { computed } from 'vue'
import type { AnswerSpec, OptionSpec } from '@/types'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { optionLabelsForAnswer } from '@/lib/answerFormat'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'

const props = defineProps<{
    answer: AnswerSpec | null | undefined
    options?: OptionSpec[] | null
    emptyText?: string
}>()

const choiceLabels = computed(() => optionLabelsForAnswer(props.answer, props.options))
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

        <!-- 旧格式未解析：只读展示原文 -->
        <template v-else-if="answer.kind === 'legacy_unresolved'">
            <div class="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/20">
                <div class="mb-1 text-xs font-medium text-amber-700 dark:text-amber-400">旧格式答案（未解析）</div>
                <RichContent :content="answer.raw" empty-text="（无内容）" class="[&_.prose]:my-0" />
            </div>
        </template>
    </div>
</template>
