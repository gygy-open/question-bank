<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Pencil, Trash2, Check, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const { $api } = useNuxtApp()

interface Prompt {
    id: number
    title: string
    content: string
}

const props = defineProps<{
    open: boolean
}>()

const emit = defineEmits(['update:open', 'select'])

const prompts = ref<Prompt[]>([])
const isLoading = ref(false)
const isEditing = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
    title: '',
    content: ''
})

const fetchPrompts = async () => {
    try {
        isLoading.value = true
        prompts.value = await $api<Prompt[]>('/chat/prompts')
    } catch (e) {
        console.error('Failed to fetch prompts', e)
    } finally {
        isLoading.value = false
    }
}

const resetForm = () => {
    form.value = { title: '', content: '' }
    isEditing.value = false
    editingId.value = null
}

const startEdit = (prompt: Prompt) => {
    form.value = { title: prompt.title, content: prompt.content }
    editingId.value = prompt.id
    isEditing.value = true
}

const savePrompt = async () => {
    if (!form.value.title || !form.value.content) return

    try {
        if (editingId.value) {
            const updated = await $api<Prompt>(`/chat/prompts/${editingId.value}`, {
                method: 'PUT',
                body: form.value
            })
            const index = prompts.value.findIndex(p => p.id === editingId.value)
            if (index !== -1) prompts.value[index] = updated
        } else {
            const created = await $api<Prompt>('/chat/prompts', {
                method: 'POST',
                body: form.value
            })
            prompts.value.push(created)
        }
        resetForm()
    } catch (e) {
        console.error('Failed to save prompt', e)
    }
}

const deletePrompt = async (id: number) => {
    if (!confirm('确定要删除这个常用指令吗？')) return
    try {
        await $api(`/chat/prompts/${id}`, { method: 'DELETE' })
        prompts.value = prompts.value.filter(p => p.id !== id)
    } catch (e) {
        console.error('Failed to delete prompt', e)
    }
}

const selectPrompt = (content: string) => {
    emit('select', content)
    emit('update:open', false)
}

onMounted(() => {
    fetchPrompts()
})
</script>

<template>
    <Dialog :open="open" @update:open="$emit('update:open', $event)">
        <DialogContent class="sm:max-w-[800px] h-[600px] flex flex-col p-0 gap-0 overflow-hidden">
            <DialogHeader class="p-6 pb-2">
                <DialogTitle>常用指令</DialogTitle>
            </DialogHeader>
            
            <div class="flex-1 flex min-h-0">
                <!-- List -->
                <div class="w-1/3 border-r flex flex-col bg-muted/10">
                    <div class="p-4 border-b">
                        <Button class="w-full justify-start gap-2" variant="outline" @click="resetForm">
                            <Plus class="w-4 h-4" />
                            新建指令
                        </Button>
                    </div>
                    <ScrollArea class="flex-1">
                        <div class="flex flex-col gap-1 p-2">
                            <div 
                                v-for="prompt in prompts" 
                                :key="prompt.id"
                                :class="[
                                    'p-3 rounded-md cursor-pointer transition-colors text-sm group relative border',
                                    editingId === prompt.id ? 'bg-accent border-primary' : 'hover:bg-accent/50 border-transparent'
                                ]"
                                @click="selectPrompt(prompt.content)"
                            >
                                <div class="font-medium truncate pr-6 mb-1">{{ prompt.title }}</div>
                                <div class="text-xs text-muted-foreground line-clamp-2">{{ prompt.content }}</div>
                                
                                <div class="absolute right-2 top-2 opacity-0 group-hover:opacity-100 flex gap-1 bg-background/80 rounded shadow-sm border">
                                    <button @click.stop="startEdit(prompt)" class="p-1.5 hover:text-primary transition-colors" title="编辑">
                                        <Pencil class="w-3 h-3" />
                                    </button>
                                    <button @click.stop="deletePrompt(prompt.id)" class="p-1.5 hover:text-destructive transition-colors" title="删除">
                                        <Trash2 class="w-3 h-3" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </ScrollArea>
                </div>

                <!-- Editor -->
                <div class="flex-1 flex flex-col p-6 gap-4 bg-background">
                    <div class="space-y-2">
                        <label class="text-sm font-medium">标题</label>
                        <Input v-model="form.title" placeholder="例如：翻译成中文" />
                    </div>
                    <div class="space-y-2 flex-1 flex flex-col min-h-0">
                        <label class="text-sm font-medium">指令内容</label>
                        <Textarea 
                            v-model="form.content" 
                            placeholder="输入指令内容..." 
                            class="flex-1 resize-none font-mono text-sm"
                        />
                    </div>
                    <div class="flex justify-end gap-2 pt-2">
                        <Button v-if="isEditing" variant="ghost" @click="resetForm">取消编辑</Button>
                        <Button @click="savePrompt" :disabled="!form.title || !form.content">
                            {{ isEditing ? '保存修改' : '添加指令' }}
                        </Button>
                    </div>
                </div>
            </div>
        </DialogContent>
    </Dialog>
</template>
