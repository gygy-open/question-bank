<script setup lang="ts">
import { Copy } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { toast } from 'vue-sonner'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', value: boolean): void }>()

const { t } = useI18n()

// 标签名、示例取值是解析器语法 / 用户写入文档的字面量，原样作为占位符参数插入，不翻译。
type RequiredLevel = 'required' | 'groupRequired' | 'optional'
const tagRows: { tag: string; required: RequiredLevel; note: string; params?: Record<string, string> }[] = [
    { tag: '【题目】', required: 'required', note: 'question' },
    { tag: '【题目材料】', required: 'groupRequired', note: 'stimulus' },
    { tag: '【题组】', required: 'groupRequired', note: 'group' },
    { tag: '【题组结束】', required: 'optional', note: 'groupEnd' },
    { tag: '【题型】', required: 'optional', note: 'type', params: { values: '单选/多选/判断/填空/解答' } },
    { tag: '【选项】', required: 'optional', note: 'options', params: { block: 'A. … B. …', perItem: '【选项A】【选项B】' } },
    { tag: '【答案】', required: 'optional', note: 'answer', params: { multiExample: 'AB', trueFalse: '对/错' } },
    { tag: '【解析】', required: 'optional', note: 'multiline' },
    { tag: '【思路】', required: 'optional', note: 'multiline' },
    { tag: '【难度】', required: 'optional', note: 'difficulty', params: { levels: '简单/中等/困难' } },
    { tag: '【小结】', required: 'optional', note: 'multiline' },
    { tag: '【答案区】', required: 'optional', note: 'answerSection', params: { aliases: '【答案表】【统一答案】【答案速查】' } },
]

const examples = [
    {
        key: 'single',
        labelKey: 'questions.types.singleChoice',
        text: `【题目】下列关于集合的说法正确的是
【选项】A. 空集是任何集合的子集  B. 0 是空集  C. {0} 是空集  D. 以上都不对
【答案】A
【解析】空集是任何集合的子集。`,
    },
    {
        key: 'truefalse',
        labelKey: 'questions.types.trueFalse',
        text: `【题目】判断：0 是自然数
【答案】对`,
    },
    {
        key: 'blank',
        labelKey: 'questions.types.fillInTheBlank',
        text: `【题目】1 + 1 = ____
【答案】2`,
    },
    {
        key: 'question-group',
        labelKey: 'templateGuide.examples.questionGroup',
        text: `【题目】卷首独立题
【答案】略

【题目材料】材料一
阅读下面的文字，完成后续题目。

这里可以包含多段 Markdown 内容。

【题组】材料一
1.【题目】请概括题目材料的主要内容
【题型】解答
【答案】略

2.【题目】下列理解正确的是
【题型】单选
【选项】A. 选项一  B. 选项二
【答案】A
【题组结束】

【题目】题组后的独立题
【答案】略`,
    },
    {
        key: 'answer-section',
        labelKey: 'templateGuide.examples.answerSection',
        text: `【题目】1+1=?
【选项】A. 1 B. 2 C. 3 D. 4
【题目】3+3=?
【选项】A. 5 B. 6 C. 7 D. 8
【答案区】
| 题号 | 1 | 2 |
|:---:|:---:|:---:|
| 答案 | B | B |
1．因为1+1=2，选B。
2．因为3+3=6，选B。`,
    },
]

const copyExample = async (text: string) => {
    await navigator.clipboard.writeText(text)
    toast.success(t('templateGuide.copied'))
}
</script>

<template>
    <Dialog :open="open" @update:open="emit('update:open', $event)">
        <DialogContent class="w-[95vw] sm:max-w-[680px] max-h-[85vh] overflow-y-auto">
            <DialogHeader>
                <DialogTitle>{{ t('templateGuide.title') }}</DialogTitle>
                <DialogDescription>
                    <i18n-t scope="global" keypath="templateGuide.description">
                        <template #question><Badge variant="outline">【题目】</Badge></template>
                        <template #stimulus><Badge variant="outline">【题目材料】</Badge></template>
                        <template #group><Badge variant="outline">【题组】</Badge></template>
                        <template #fullwidth>【】</template>
                        <template #halfwidth>[]</template>
                    </i18n-t>
                </DialogDescription>
            </DialogHeader>

            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead class="w-28">{{ t('templateGuide.table.tag') }}</TableHead>
                        <TableHead class="w-16">{{ t('templateGuide.table.required') }}</TableHead>
                        <TableHead>{{ t('templateGuide.table.note') }}</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    <TableRow v-for="row in tagRows" :key="row.tag">
                        <TableCell><Badge variant="outline">{{ row.tag }}</Badge></TableCell>
                        <TableCell>
                            <Badge :variant="row.required === 'required' ? 'default' : 'secondary'">{{ t(`templateGuide.required.${row.required}`) }}</Badge>
                        </TableCell>
                        <TableCell class="text-sm text-muted-foreground">{{ t(`templateGuide.notes.${row.note}`, row.params ?? {}) }}</TableCell>
                    </TableRow>
                </TableBody>
            </Table>

            <Tabs default-value="single" class="mt-2">
                <TabsList class="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-5">
                    <TabsTrigger v-for="ex in examples" :key="ex.key" :value="ex.key">{{ t(ex.labelKey) }}</TabsTrigger>
                </TabsList>
                <TabsContent v-for="ex in examples" :key="ex.key" :value="ex.key" class="mt-3">
                    <div class="relative rounded-md border bg-muted/30">
                        <pre class="whitespace-pre-wrap break-all p-4 pr-12 text-sm font-mono">{{ ex.text }}</pre>
                        <Button
                            variant="ghost"
                            size="sm"
                            class="absolute right-2 top-2"
                            @click="copyExample(ex.text)"
                        >
                            <Copy class="h-4 w-4 mr-1" />{{ t('common.copy') }}
                        </Button>
                    </div>
                </TabsContent>
            </Tabs>
        </DialogContent>
    </Dialog>
</template>
