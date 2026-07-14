<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAPI } from '~/composables/useAPI'
import type { Tag, TagCategory } from '~/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Plus, Pencil, Trash2, Settings } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

// State
const { $api } = useNuxtApp()
const { data: tags, refresh } = await useAPI<Tag[]>('/tags')
const { data: tagCategories, refresh: refreshCategories } = await useAPI<TagCategory[]>('/tag-categories')

const selectedCategory = ref('all')
const selectedTags = ref<number[]>([])
const isDialogOpen = ref(false)
const isEditing = ref(false)
const currentTag = ref<Partial<Tag>>({
    name: '',
    category: 'general',
    color: '#grey'
})

// Category Management State
const isCategoryDialogOpen = ref(false)
const editingCategoryId = ref<number | null>(null)
const editingCategory = ref<Partial<TagCategory>>({})
const newCategory = ref<Partial<TagCategory>>({
    name: '',
    slug: '',
    sort_order: 0,
    is_active: true
})

// Computed
const categories = computed(() => {
    return tagCategories.value?.map(c => ({ value: c.slug, label: c.name })) || []
})

const filteredTags = computed(() => {
    if (!tags.value) return []
    if (selectedCategory.value === 'all') return tags.value
    return tags.value.filter(tag => tag.category === selectedCategory.value)
})

const isAllSelected = computed(() => {
    return filteredTags.value.length > 0 && filteredTags.value.every(t => selectedTags.value.includes(t.id))
})

// Actions
const openCreateDialog = () => {
    isEditing.value = false
    currentTag.value = { name: '', category: 'general', color: '#grey' }
    isDialogOpen.value = true
}

const openEditDialog = (tag: Tag) => {
    isEditing.value = true
    currentTag.value = { ...tag }
    isDialogOpen.value = true
}

const saveTag = async () => {
    try {
        if (isEditing.value && currentTag.value.id) {
            await $api(`/tags/${currentTag.value.id}`, {
                method: 'PUT',
                body: currentTag.value
            })
            toast.success('标签更新成功')
        } else {
            await $api('/tags', {
                method: 'POST',
                body: currentTag.value
            })
            toast.success('标签创建成功')
        }
        await refresh()
        isDialogOpen.value = false
    } catch (error: any) {
        console.error('Failed to save tag', error)
        toast.error(error.data?.detail || '保存标签失败')
    }
}

const deleteTag = async (id: number) => {
    if (!confirm('确定要删除这个标签吗？')) return
    try {
        await $api(`/tags/${id}`, { method: 'DELETE' })
        await refresh()
    } catch (error) {
        console.error('Failed to delete tag', error)
    }
}

const toggleSelectAll = (checked: boolean) => {
    if (checked) {
        selectedTags.value = filteredTags.value.map(t => t.id)
    } else {
        selectedTags.value = []
    }
}

const toggleSelect = (id: number, checked: boolean) => {
    if (checked) {
        if (!selectedTags.value.includes(id)) {
            selectedTags.value = [...selectedTags.value, id]
        }
    } else {
        selectedTags.value = selectedTags.value.filter(tid => tid !== id)
    }
}

const batchDelete = async () => {
    if (selectedTags.value.length === 0) return
    if (!confirm(`确定要删除选中的 ${selectedTags.value.length} 个标签吗？`)) return

    try {
        await Promise.all(selectedTags.value.map(id => $api(`/tags/${id}`, { method: 'DELETE' })))
        toast.success(`成功删除 ${selectedTags.value.length} 个标签`)
        selectedTags.value = []
        await refresh()
    } catch (error) {
        console.error('Batch delete failed', error)
        toast.error('批量删除失败')
    }
}

// Category Actions
const startEditCategory = (category: TagCategory) => {
    editingCategoryId.value = category.id
    editingCategory.value = { ...category }
}

const cancelEditCategory = () => {
    editingCategoryId.value = null
    editingCategory.value = {}
}

const saveCategory = async () => {
    if (!editingCategoryId.value) return
    try {
        await $api(`/tag-categories/${editingCategoryId.value}`, {
            method: 'PUT',
            body: editingCategory.value
        })
        await refreshCategories()
        editingCategoryId.value = null
        editingCategory.value = {}
    } catch (error) {
        console.error('Failed to update category', error)
    }
}

const createCategory = async () => {
    try {
        await $api('/tag-categories', {
            method: 'POST',
            body: newCategory.value
        })
        await refreshCategories()
        newCategory.value = { name: '', slug: '', sort_order: 0, is_active: true }
    } catch (error) {
        console.error('Failed to create category', error)
    }
}

const deleteCategory = async (id: number) => {
    if (!confirm('确定要删除这个分类吗？这将同时删除该分类下的所有标签！')) return
    try {
        await $api(`/tag-categories/${id}`, { method: 'DELETE' })
        await refreshCategories()
        toast.success('分类删除成功')
    } catch (error) {
        console.error('Failed to delete category', error)
        toast.error('删除分类失败')
    }
}
</script>

<template>
    <PageHeader title="标签管理">
        <template #actions>
            <Button variant="outline" class="mr-2" @click="isCategoryDialogOpen = true">
                <Settings class="w-4 h-4 mr-2" />
                管理分类
            </Button>
            <Button @click="openCreateDialog">
                <Plus class="w-4 h-4 mr-2" />
                新建标签
            </Button>
        </template>
    </PageHeader>
    <div class="flex flex-1 flex-col">
        <div class="@container/main flex flex-1 flex-col px-4 space-y-6 py-6">
            <Tabs v-model="selectedCategory" class="w-full">
                <div class="flex justify-between items-center mb-4">
                    <TabsList class="flex flex-wrap h-auto">
                        <TabsTrigger value="all">全部</TabsTrigger>
                        <TabsTrigger v-for="cat in categories" :key="cat.value" :value="cat.value">
                            {{ cat.label }}
                        </TabsTrigger>
                    </TabsList>
                    <Button v-if="selectedTags.length > 0" variant="destructive" size="sm" @click="batchDelete">
                        <Trash2 class="w-4 h-4 mr-2" />
                        批量删除 ({{ selectedTags.length }})
                    </Button>
                </div>

                <div class="border rounded-md">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead class="w-[50px]">
                                    <Checkbox 
                                        :checked="isAllSelected"
                                        @update:model-value="(v) => toggleSelectAll(v as boolean)"
                                    />
                                </TableHead>
                                <TableHead>ID</TableHead>
                                <TableHead>名称</TableHead>
                                <TableHead>分类</TableHead>
                                <TableHead>颜色</TableHead>
                                <TableHead class="text-right">操作</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            <TableRow v-for="tag in filteredTags" :key="tag.id">
                                <TableCell>
                                    <Checkbox 
                                        :checked="selectedTags.includes(tag.id)"
                                        @update:model-value="(v) => toggleSelect(tag.id, v as boolean)"
                                    />
                                </TableCell>
                                <TableCell>{{ tag.id }}</TableCell>
                                <TableCell>
                                    <Badge variant="outline" :style="{ borderColor: tag.color, color: tag.color }">
                                        {{ tag.name }}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    <Badge variant="secondary">{{categories.find(c => c.value === tag.category)?.label
                                        ||
                                        tag.category }}</Badge>
                                </TableCell>
                                <TableCell>
                                    <div class="flex items-center gap-2">
                                        <div class="w-4 h-4 rounded-full border"
                                            :style="{ backgroundColor: tag.color }">
                                        </div>
                                        <span class="text-sm text-muted-foreground">{{ tag.color }}</span>
                                    </div>
                                </TableCell>
                                <TableCell class="text-right">
                                    <div class="flex justify-end gap-2">
                                        <Button variant="ghost" size="icon" @click="openEditDialog(tag)">
                                            <Pencil class="w-4 h-4" />
                                        </Button>
                                        <Button variant="ghost" size="icon" class="text-destructive"
                                            @click="deleteTag(tag.id)">
                                            <Trash2 class="w-4 h-4" />
                                        </Button>
                                    </div>
                                </TableCell>
                            </TableRow>
                            <TableRow v-if="filteredTags.length === 0">
                                <TableCell colspan="5" class="text-center py-8 text-muted-foreground">
                                    暂无标签
                                </TableCell>
                            </TableRow>
                        </TableBody>
                    </Table>
                </div>
            </Tabs>

            <Dialog v-model:open="isDialogOpen">
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{{ isEditing ? '编辑标签' : '新建标签' }}</DialogTitle>
                        <DialogDescription>
                            配置标签的名称、分类和颜色。
                        </DialogDescription>
                    </DialogHeader>

                    <div class="grid gap-4 py-4">
                        <div class="grid gap-2">
                            <label>名称</label>
                            <Input v-model="currentTag.name" placeholder="例如：2023, 高考, 易错题" />
                        </div>

                        <div class="grid gap-2">
                            <label>分类</label>
                            <Select v-model="currentTag.category">
                                <SelectTrigger>
                                    <SelectValue placeholder="选择分类" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem v-for="cat in categories" :key="cat.value" :value="cat.value">
                                        {{ cat.label }}
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div class="grid gap-2">
                            <label>颜色</label>
                            <div class="flex gap-2">
                                <Input v-model="currentTag.color" type="color" class="w-12 p-1 h-10" />
                                <Input v-model="currentTag.color" placeholder="#000000" />
                            </div>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" @click="isDialogOpen = false">取消</Button>
                        <Button @click="saveTag">保存</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <!-- Category Management Dialog -->
            <Dialog v-model:open="isCategoryDialogOpen">
                <DialogContent class="max-w-3xl">
                    <DialogHeader>
                        <DialogTitle>管理标签分类</DialogTitle>
                        <DialogDescription>
                            添加、编辑或删除标签分类。
                        </DialogDescription>
                    </DialogHeader>
                    
                    <div class="grid gap-4 py-4">
                        <div class="border rounded-md">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>名称</TableHead>
                                        <TableHead>代码 (Slug)</TableHead>
                                        <TableHead>排序</TableHead>
                                        <TableHead class="text-right">操作</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    <TableRow v-for="cat in tagCategories" :key="cat.id">
                                        <TableCell>
                                            <Input v-if="editingCategoryId === cat.id" v-model="editingCategory.name" />
                                            <span v-else>{{ cat.name }}</span>
                                        </TableCell>
                                        <TableCell>
                                            <Input v-if="editingCategoryId === cat.id" v-model="editingCategory.slug" />
                                            <span v-else>{{ cat.slug }}</span>
                                        </TableCell>
                                        <TableCell>
                                            <Input v-if="editingCategoryId === cat.id" v-model="editingCategory.sort_order" type="number" />
                                            <span v-else>{{ cat.sort_order }}</span>
                                        </TableCell>
                                        <TableCell class="text-right">
                                            <div class="flex justify-end gap-2">
                                                <template v-if="editingCategoryId === cat.id">
                                                    <Button size="sm" @click="saveCategory">保存</Button>
                                                    <Button size="sm" variant="ghost" @click="cancelEditCategory">取消</Button>
                                                </template>
                                                <template v-else>
                                                    <Button variant="ghost" size="icon" @click="startEditCategory(cat)">
                                                        <Pencil class="w-4 h-4" />
                                                    </Button>
                                                    <Button variant="ghost" size="icon" class="text-destructive" @click="deleteCategory(cat.id)">
                                                        <Trash2 class="w-4 h-4" />
                                                    </Button>
                                                </template>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                    <!-- New Category Row -->
                                    <TableRow>
                                        <TableCell>
                                            <Input v-model="newCategory.name" placeholder="新分类名称" />
                                        </TableCell>
                                        <TableCell>
                                            <Input v-model="newCategory.slug" placeholder="slug" />
                                        </TableCell>
                                        <TableCell>
                                            <Input v-model="newCategory.sort_order" type="number" placeholder="0" />
                                        </TableCell>
                                        <TableCell class="text-right">
                                            <Button size="sm" @click="createCategory" :disabled="!newCategory.name || !newCategory.slug">添加</Button>
                                        </TableCell>
                                    </TableRow>
                                </TableBody>
                            </Table>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    </div>
</template>
