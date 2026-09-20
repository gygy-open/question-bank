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

const tagRows = [
    { tag: '【题目】', required: '必填', note: '每道题的开头，同时作为题目之间的分隔符' },
    { tag: '【题目材料】', required: '题组必填', note: '声明多行题目材料；名称可选，复用时填写名称' },
    { tag: '【题组】', required: '题组必填', note: '开始题组；名称省略时引用最近声明的题目材料' },
    { tag: '【题组结束】', required: '可选', note: '结束题组，后续题目恢复为独立题；新题组、题目材料或大题标题也会自动结束当前题组' },
    { tag: '【题型】', required: '可选', note: '单选/多选/判断/填空/解答；省略时自动推断' },
    { tag: '【选项】', required: '可选', note: '块写法 A. … B. … 或逐项 【选项A】【选项B】' },
    { tag: '【答案】', required: '可选', note: '选择题写字母（多选如 AB），判断题写 对/错' },
    { tag: '【解析】', required: '可选', note: '可多行' },
    { tag: '【思路】', required: '可选', note: '可多行' },
    { tag: '【难度】', required: '可选', note: '1–5，或 简单/中等/困难' },
    { tag: '【小结】', required: '可选', note: '可多行' },
    { tag: '【答案区】', required: '可选', note: '别名【答案表】【统一答案】【答案速查】；用于文末统一答案表' },
]

const examples = [
    {
        key: 'single',
        label: '单选题',
        text: `【题目】下列关于集合的说法正确的是
【选项】A. 空集是任何集合的子集  B. 0 是空集  C. {0} 是空集  D. 以上都不对
【答案】A
【解析】空集是任何集合的子集。`,
    },
    {
        key: 'truefalse',
        label: '判断题',
        text: `【题目】判断：0 是自然数
【答案】对`,
    },
    {
        key: 'blank',
        label: '填空题',
        text: `【题目】1 + 1 = ____
【答案】2`,
    },
    {
        key: 'question-group',
        label: '材料题组',
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
        label: '统一答案区',
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
    toast.success('已复制，可直接粘贴到文档中')
}
</script>

<template>
    <Dialog :open="open" @update:open="emit('update:open', $event)">
        <DialogContent class="w-[95vw] sm:max-w-[680px] max-h-[85vh] overflow-y-auto">
            <DialogHeader>
                <DialogTitle>标签精准解析：格式说明</DialogTitle>
                <DialogDescription>
                    独立题用 <Badge variant="outline">【题目】</Badge> 分隔；材料题组使用
                    <Badge variant="outline">【题目材料】</Badge> 和 <Badge variant="outline">【题组】</Badge>。
                    全角【】与半角 [] 均可识别。
                </DialogDescription>
            </DialogHeader>

            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead class="w-28">标签</TableHead>
                        <TableHead class="w-16">是否必填</TableHead>
                        <TableHead>说明</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    <TableRow v-for="row in tagRows" :key="row.tag">
                        <TableCell><Badge variant="outline">{{ row.tag }}</Badge></TableCell>
                        <TableCell>
                            <Badge :variant="row.required === '必填' ? 'default' : 'secondary'">{{ row.required }}</Badge>
                        </TableCell>
                        <TableCell class="text-sm text-muted-foreground">{{ row.note }}</TableCell>
                    </TableRow>
                </TableBody>
            </Table>

            <Tabs default-value="single" class="mt-2">
                <TabsList class="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-5">
                    <TabsTrigger v-for="ex in examples" :key="ex.key" :value="ex.key">{{ ex.label }}</TabsTrigger>
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
                            <Copy class="h-4 w-4 mr-1" />复制
                        </Button>
                    </div>
                </TabsContent>
            </Tabs>
        </DialogContent>
    </Dialog>
</template>
