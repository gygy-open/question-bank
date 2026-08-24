<script setup lang="ts">
import { computed, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Eraser, Plus, Trash2, X, RotateCcw } from '@lucide/vue'
import type { AnswerSpec, Blank, OptionSpec, QuestionType, RichDoc } from '@/types'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { collectBlankIds, generateBlankId } from '@/components/rich-editor/richDoc'
import { createDefaultAnswer, fillBlanksFromStem } from '@/lib/questionModel'

const model = defineModel<AnswerSpec | null>({ default: null })

const props = defineProps<{
    qType: QuestionType
    options?: OptionSpec[]
    stem?: RichDoc
}>()

const options = computed<OptionSpec[]>(() => props.options ?? [])

// stem 含 blank 节点时，填空数量/顺序由题干驱动（不可手动增删）。
const stemBlankIds = computed(() => collectBlankIds(props.stem ?? null))
const stemDriven = computed(() => stemBlankIds.value.length > 0)

// 题干填空变化时，同步 answer.blanks 的 id/顺序，保留已有 accept。
watch(
    () => stemBlankIds.value.join('|'),
    () => {
        if (props.qType !== 'fill_in_the_blank') return
        const current = model.value?.kind === 'fill_in_the_blank' ? model.value.blanks : undefined
        const synced = fillBlanksFromStem(props.stem ?? null, current)
        model.value = { kind: 'fill_in_the_blank', blanks: synced }
    },
)

// --- single choice ---
const singleCorrect = computed<string>({
    get: () => (model.value?.kind === 'single_choice' ? model.value.correct : ''),
    set: (v) => {
        model.value = { kind: 'single_choice', correct: v }
    },
})

// --- multiple choice ---
const multipleCorrect = computed<string[]>(() =>
    model.value?.kind === 'multiple_choice' ? model.value.correct : [],
)
function toggleMultiple(id: string, checked: boolean | 'indeterminate') {
    const set = new Set(multipleCorrect.value)
    if (checked) set.add(id)
    else set.delete(id)
    const grading = model.value?.kind === 'multiple_choice' ? model.value.grading : null
    model.value = { kind: 'multiple_choice', correct: [...set], grading }
}

// --- true / false ---
const trueFalseValue = computed<string>({
    get: () => (model.value?.kind === 'true_false' ? String(model.value.correct) : ''),
    set: (v) => {
        model.value = { kind: 'true_false', correct: v === 'true' }
    },
})

// --- fill in the blank ---
const blanks = computed<Blank[]>(() =>
    model.value?.kind === 'fill_in_the_blank' ? model.value.blanks : [],
)
function commitBlanks(next: Blank[]) {
    model.value = { kind: 'fill_in_the_blank', blanks: next }
}
function setAccept(blankIdx: number, acceptIdx: number, doc: RichDoc) {
    const next = blanks.value.map((b, i) =>
        i === blankIdx
            ? { ...b, accept: b.accept.map((a, j) => (j === acceptIdx ? doc : a)) }
            : b,
    )
    commitBlanks(next)
}
function addAccept(blankIdx: number) {
    const next = blanks.value.map((b, i) =>
        i === blankIdx ? { ...b, accept: [...b.accept, null] } : b,
    )
    commitBlanks(next)
}
function removeAccept(blankIdx: number, acceptIdx: number) {
    const next = blanks.value.map((b, i) =>
        i === blankIdx ? { ...b, accept: b.accept.filter((_, j) => j !== acceptIdx) } : b,
    )
    commitBlanks(next)
}
function addBlank() {
    commitBlanks([...blanks.value, { id: generateBlankId(), accept: [null] }])
}
function removeBlank(blankIdx: number) {
    commitBlanks(blanks.value.filter((_, i) => i !== blankIdx))
}

// --- free response ---
const freeReference = computed<RichDoc>({
    get: () => (model.value?.kind === 'free_response' ? model.value.reference : null),
    set: (v) => {
        model.value = { kind: 'free_response', reference: v }
    },
})

// --- legacy unresolved ---
function refillFromLegacy() {
    const expected =
        model.value?.kind === 'legacy_unresolved' ? model.value.expected_kind : props.qType
    model.value = createDefaultAnswer(expected, options.value, props.stem ?? null)
}

function clearAnswer() {
    model.value = null
}
</script>

<template>
    <div class="space-y-2">
        <div class="flex items-center justify-between gap-2">
            <Label>答案</Label>
            <Button
                v-if="model && model.kind !== 'legacy_unresolved'"
                variant="ghost"
                size="sm"
                class="h-7 text-muted-foreground"
                @click="clearAnswer"
            >
                <Eraser class="mr-1 h-3.5 w-3.5" /> 暂不填写
            </Button>
        </div>

        <!-- 旧格式未解析：只读原文 + 重新填写 -->
        <div v-if="model && model.kind === 'legacy_unresolved'" class="space-y-2">
            <AnswerDisplay :answer="model" :options="options" />
            <Button variant="outline" size="sm" @click="refillFromLegacy">
                <RotateCcw class="mr-1 h-3.5 w-3.5" /> 重新填写答案
            </Button>
        </div>

        <!-- 单选 -->
        <RadioGroup v-else-if="qType === 'single_choice'" v-model="singleCorrect" class="space-y-1.5">
            <div
                v-for="opt in options"
                :key="opt.id"
                class="flex items-start gap-2 rounded-md border border-transparent px-2 py-1.5 hover:bg-muted/40"
            >
                <RadioGroupItem :value="opt.id" :id="`ans-${opt.id}`" class="mt-1" />
                <Label :for="`ans-${opt.id}`" class="flex flex-1 cursor-pointer items-start gap-2 font-normal">
                    <span class="font-semibold text-muted-foreground">{{ opt.label }}.</span>
                    <RichContent :content="opt.content" empty-text="（空选项）" class="[&_.prose]:my-0 [&_.prose>p]:my-0" />
                </Label>
            </div>
            <p v-if="options.length === 0" class="text-xs text-muted-foreground">请先添加选项</p>
        </RadioGroup>

        <!-- 多选 -->
        <div v-else-if="qType === 'multiple_choice'" class="space-y-1.5">
            <div
                v-for="opt in options"
                :key="opt.id"
                class="flex items-start gap-2 rounded-md border border-transparent px-2 py-1.5 hover:bg-muted/40"
            >
                <Checkbox
                    :id="`ans-${opt.id}`"
                    :model-value="multipleCorrect.includes(opt.id)"
                    class="mt-1"
                    @update:model-value="(v) => toggleMultiple(opt.id, v)"
                />
                <Label :for="`ans-${opt.id}`" class="flex flex-1 cursor-pointer items-start gap-2 font-normal">
                    <span class="font-semibold text-muted-foreground">{{ opt.label }}.</span>
                    <RichContent :content="opt.content" empty-text="（空选项）" class="[&_.prose]:my-0 [&_.prose>p]:my-0" />
                </Label>
            </div>
            <p v-if="options.length === 0" class="text-xs text-muted-foreground">请先添加选项</p>
        </div>

        <!-- 判断 -->
        <RadioGroup v-else-if="qType === 'true_false'" v-model="trueFalseValue" class="flex gap-6">
            <div class="flex items-center gap-2">
                <RadioGroupItem value="true" id="ans-tf-true" />
                <Label for="ans-tf-true" class="cursor-pointer font-normal">正确</Label>
            </div>
            <div class="flex items-center gap-2">
                <RadioGroupItem value="false" id="ans-tf-false" />
                <Label for="ans-tf-false" class="cursor-pointer font-normal">错误</Label>
            </div>
        </RadioGroup>

        <!-- 填空 -->
        <div v-else-if="qType === 'fill_in_the_blank'" class="space-y-3">
            <p v-if="stemDriven" class="text-xs text-muted-foreground">
                填空数量与顺序由题干中的填空占位符决定，可为每空设置多个可接受答案。
            </p>
            <div
                v-for="(blank, bIdx) in blanks"
                :key="blank.id"
                class="rounded-md border bg-muted/20 p-3"
            >
                <div class="mb-2 flex items-center justify-between">
                    <Label class="text-sm">第 {{ bIdx + 1 }} 空（可接受答案）</Label>
                    <Button
                        v-if="!stemDriven"
                        variant="ghost"
                        size="icon"
                        class="h-6 w-6"
                        :disabled="blanks.length <= 1"
                        @click="removeBlank(bIdx)"
                    >
                        <Trash2 class="h-3 w-3" />
                    </Button>
                </div>
                <div class="space-y-2">
                    <div v-for="(acc, aIdx) in blank.accept" :key="aIdx" class="flex items-start gap-2">
                        <div class="flex-1">
                            <RichEditor
                                :model-value="acc"
                                placeholder="输入参考答案…"
                                @update:model-value="(v) => setAccept(bIdx, aIdx, v)"
                            />
                        </div>
                        <Button
                            variant="ghost"
                            size="icon"
                            class="mt-1 h-8 w-8 shrink-0"
                            :disabled="blank.accept.length <= 1"
                            @click="removeAccept(bIdx, aIdx)"
                        >
                            <X class="h-4 w-4" />
                        </Button>
                    </div>
                    <Button variant="outline" size="sm" class="h-8 w-full border-dashed" @click="addAccept(bIdx)">
                        <Plus class="mr-1 h-3 w-3" /> 添加备选答案
                    </Button>
                </div>
            </div>
            <Button v-if="!stemDriven" variant="outline" class="w-full border-dashed" @click="addBlank">
                <Plus class="mr-2 h-4 w-4" /> 添加填空项
            </Button>
        </div>

        <!-- 解答 -->
        <div v-else-if="qType === 'free_response'">
            <RichEditor v-model="freeReference" placeholder="输入参考答案 / 解答…" />
        </div>
    </div>
</template>