<script setup lang="ts">
import { computed } from 'vue'
import type { TagCategory } from '~/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Plus, Pencil, Trash2, Info, Tag } from '@lucide/vue'

const props = withDefaults(defineProps<{
    categories: TagCategory[]
    disabled?: boolean
}>(), {
    disabled: false,
})

const emit = defineEmits<{
    (e: 'create'): void
    (e: 'save-edit'): void
    (e: 'delete', id: number): void
    (e: 'create-tag', categoryId: number): void
}>()

// Selection + inline edit/add form state is owned by the parent page (which performs the API calls).
const selected = defineModel<number | 'all'>('selected', { required: true })
const editingId = defineModel<number | null>('editingId', { default: null })
const editingForm = defineModel<Partial<TagCategory>>('editingForm', { default: () => ({}) })
const isAdding = defineModel<boolean>('isAdding', { default: false })
const newCategoryForm = defineModel<Partial<TagCategory>>('newCategoryForm', { default: () => ({}) })

const sortedCategories = computed(() =>
    [...props.categories].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
)

const startEdit = (cat: TagCategory) => {
    editingId.value = cat.id
    editingForm.value = { ...cat }
}

const cancelEdit = () => {
    editingId.value = null
    editingForm.value = {}
}

const cancelAdd = () => {
    isAdding.value = false
    newCategoryForm.value = { name: '', sort_order: 0, is_active: true }
}
</script>

<template>
    <nav aria-label="标签分类" class="flex flex-col">
        <div class="mb-1 flex items-center justify-between gap-1 px-2">
            <div class="flex items-center gap-1">
                <span class="text-xs font-medium text-muted-foreground">分类</span>
                <TooltipProvider :delay-duration="300">
                    <Tooltip>
                        <TooltipTrigger as-child>
                            <button type="button" class="text-muted-foreground/70 hover:text-foreground" aria-label="什么是分类？">
                                <Info class="h-3 w-3" />
                            </button>
                        </TooltipTrigger>
                        <TooltipContent side="right" class="max-w-64">
                            分类用于给标签分组（如"难度""来源""题型"），标签必须归属一个分类，方便按维度筛选、在题目里快速找标签。
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
            <Popover :open="isAdding" @update:open="(v) => !v && cancelAdd()">
                <PopoverTrigger as-child>
                    <Button variant="ghost" size="icon" class="h-5 w-5" :disabled="disabled" aria-label="新建分类" title="新建分类" @click="isAdding = true">
                        <Plus class="h-3.5 w-3.5" />
                    </Button>
                </PopoverTrigger>
                <PopoverContent side="right" align="start" class="w-64 space-y-2 p-2">
                    <Input v-model="newCategoryForm.name" placeholder="分类名称" aria-label="新分类名称" autofocus />
                    <div class="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" @click="cancelAdd">取消</Button>
                        <Button size="sm" :disabled="!newCategoryForm.name" @click="emit('create')">添加</Button>
                    </div>
                </PopoverContent>
            </Popover>
        </div>

        <button
            type="button"
            class="mb-1 flex shrink-0 items-center rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
            :class="selected === 'all' && 'bg-accent font-medium text-accent-foreground'"
            :aria-current="selected === 'all' ? 'true' : undefined"
            @click="selected = 'all'"
        >
            全部
        </button>

        <ul role="list" class="max-h-80 space-y-0.5 overflow-y-auto">
            <li v-for="cat in sortedCategories" :key="cat.id" class="group">
                <div
                    v-if="editingId === cat.id"
                    class="space-y-2 rounded-md border bg-muted/40 p-2"
                    @keydown.esc="cancelEdit"
                >
                    <Input v-model="editingForm.name" placeholder="名称" aria-label="分类名称" />
                    <Input v-model="editingForm.sort_order" type="number" placeholder="排序" aria-label="排序" />
                    <div class="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" @click="cancelEdit">取消</Button>
                        <Button size="sm" :disabled="!editingForm.name?.trim()" @click="emit('save-edit')">保存</Button>
                    </div>
                </div>
                <div
                    v-else
                    class="flex items-center rounded-md"
                    :class="selected === cat.id && 'bg-accent text-accent-foreground'"
                >
                    <button
                        type="button"
                        class="flex min-w-0 flex-1 items-center rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                        :aria-current="selected === cat.id ? 'true' : undefined"
                        @click="selected = cat.id"
                    >
                        <span class="truncate" :class="selected === cat.id && 'font-medium'">{{ cat.name }}</span>
                    </button>
                    <div class="flex shrink-0 gap-0.5 pr-1 opacity-0 focus-within:opacity-100 group-hover:opacity-100">
                        <TooltipProvider :delay-duration="300">
                            <Tooltip>
                                <TooltipTrigger as-child>
                                    <Button variant="ghost" size="icon" class="h-6 w-6" :aria-label="`在｜${cat.name}｜下新建标签`" @click.stop="emit('create-tag', cat.id)">
                                        <Tag class="h-3 w-3" />
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent side="right">在此分类下新建标签</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                        <Button variant="ghost" size="icon" class="h-6 w-6" :aria-label="`编辑分类 ${cat.name}`" @click.stop="startEdit(cat)">
                            <Pencil class="h-3 w-3" />
                        </Button>
                        <Button variant="ghost" size="icon" class="h-6 w-6 text-destructive hover:text-destructive" :aria-label="`删除分类 ${cat.name}`" @click.stop="emit('delete', cat.id)">
                            <Trash2 class="h-3 w-3" />
                        </Button>
                    </div>
                </div>
            </li>
            <li v-if="sortedCategories.length === 0" class="px-2 py-4 text-center text-sm text-muted-foreground">
                暂无分类
            </li>
        </ul>
    </nav>
</template>
