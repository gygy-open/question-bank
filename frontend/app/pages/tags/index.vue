<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAPI } from '~/composables/useAPI'
import type { Tag, TagCategory, TagPage } from '~/types'
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
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from '@/components/ui/sheet'
import TagCategorySidebar from '@/components/manager/TagCategorySidebar.vue'
import TagImportDialog from '@/components/manager/TagImportDialog.vue'
import { Plus, Pencil, Trash2, ChevronDown, ChevronLeft, ChevronRight, Upload } from '@lucide/vue'
import {
    Pagination,
    PaginationEllipsis,
    PaginationContent,
    PaginationItem,
    PaginationNext,
    PaginationPrevious,
} from '@/components/ui/pagination'
import { toast } from 'vue-sonner'

// State
const { $api } = useNuxtApp()
const { currentSubjectId, currentSubject, hasSubjects } = useSubjectContext()

const page = ref(1)
const pageSize = ref(20)
const selectedCategory = ref<number | 'all'>('all')
const selectedTags = ref<number[]>([])

const { data: tagsPage, refresh } = await useAPI<TagPage>('/tags', {
  query: computed(() => ({
    subject_id: currentSubjectId.value || undefined,
    page: page.value,
    size: pageSize.value,
    category_id: selectedCategory.value !== 'all' ? selectedCategory.value : undefined,
  })),
  immediate: false,
  watch: false,
})
const { data: tagCategories, refresh: refreshCategories } = await useAPI<TagCategory[]>('/tag-categories', {
  query: computed(() => ({
    subject_id: currentSubjectId.value || undefined
  })),
  immediate: false,
  watch: false,
})

const tags = computed(() => tagsPage.value?.items || [])
const total = computed(() => tagsPage.value?.total || 0)

// Only fetch once a real subject is selected (never send an empty subject_id).
watch(currentSubjectId, () => {
    page.value = 1
    if (currentSubjectId.value) {
      refresh()
      refreshCategories()
    }
}, { immediate: true })

// Category filtering and paging both live server-side now; refetch on change and reset to page 1 when the category changes.
watch(selectedCategory, () => {
    page.value = 1
})
watch([page, pageSize, selectedCategory], () => {
    selectedTags.value = []
    if (currentSubjectId.value) refresh()
})
const isDialogOpen = ref(false)
const isEditing = ref(false)
const currentTag = ref<Partial<Tag>>({
    name: '',
    category_id: null,
    color: '#grey'
})

// Category Management State (sidebar owns the inline add/edit form UI, this page owns the API calls)
const editingCategoryId = ref<number | null>(null)
const editingCategory = ref<Partial<TagCategory>>({})
const isAddingCategory = ref(false)
const newCategory = ref<Partial<TagCategory>>({
    name: '',
    sort_order: 0,
    is_active: true
})
const isMobileCategorySheetOpen = ref(false)
const isImportOpen = ref(false)

// Computed
const categories = computed(() => {
    return tagCategories.value?.map(c => ({ value: c.id, label: c.name })) || []
})

const currentCategoryLabel = computed(() => {
    if (selectedCategory.value === 'all') return '全部'
    return categories.value.find(c => c.value === selectedCategory.value)?.label || '未分类'
})

// Select 组件用字符串值，'none' 代表未分类（category_id = null）
const categorySelectValue = computed<string>({
    get: () => currentTag.value.category_id != null ? String(currentTag.value.category_id) : 'none',
    set: (v) => { currentTag.value.category_id = v === 'none' ? null : Number(v) }
})

const isAllPageSelected = computed(() => {
    return tags.value.length > 0 && tags.value.every(t => selectedTags.value.includes(t.id))
})

// Actions
const openCreateDialog = () => {
    isEditing.value = false
    currentTag.value = {
        name: '',
        category_id: selectedCategory.value !== 'all' ? selectedCategory.value : null,
        color: '#grey'
    }
    isDialogOpen.value = true
}

const openEditDialog = (tag: Tag) => {
    isEditing.value = true
    currentTag.value = { ...tag }
    isDialogOpen.value = true
}

const openCreateDialogForCategory = (categoryId: number) => {
    isEditing.value = false
    currentTag.value = { name: '', category_id: categoryId, color: '#grey' }
    isDialogOpen.value = true
    isMobileCategorySheetOpen.value = false
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
                body: { ...currentTag.value, subject_id: currentSubjectId.value }
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
        // Deleting the last tag on a page (not page 1) would otherwise leave an empty page.
        if (tags.value.length === 0 && page.value > 1) page.value -= 1
    } catch (error) {
        console.error('Failed to delete tag', error)
    }
}

const toggleAllPage = (checked: boolean) => {
    if (checked) {
        selectedTags.value = tags.value.map(t => t.id)
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
        // Batch-deleting the rest of a page (not page 1) would otherwise leave an empty page.
        if (tags.value.length === 0 && page.value > 1) page.value -= 1
    } catch (error) {
        console.error('Batch delete failed', error)
        toast.error('批量删除失败')
    }
}

// Category Actions
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
        toast.success('分类更新成功')
    } catch (error: any) {
        console.error('Failed to update category', error)
        toast.error(error.data?.detail || '更新分类失败')
    }
}

const createCategory = async () => {
    if (!currentSubjectId.value) {
        toast.error('请先选择学科')
        return
    }

    try {
        await $api('/tag-categories', {
            method: 'POST',
            body: {
                ...newCategory.value,
                subject_id: currentSubjectId.value
            }
        })
        await refreshCategories()
        newCategory.value = { name: '', sort_order: 0, is_active: true }
        isAddingCategory.value = false
        toast.success('分类创建成功')
    } catch (error: any) {
        console.error('Failed to create category', error)
        toast.error(error.data?.detail || '创建分类失败')
    }
}

const deleteCategory = async (id: number) => {
    if (!confirm('确定要删除这个分类吗？这将同时删除该分类下的所有标签！')) return
    try {
        await $api(`/tag-categories/${id}`, { method: 'DELETE' })
        await refreshCategories()
        if (selectedCategory.value === id) {
            selectedCategory.value = 'all'
        }
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
            <Button variant="outline" :disabled="!hasSubjects" @click="isImportOpen = true">
                <Upload class="w-4 h-4 mr-2" />
                批量导入
            </Button>
            <Button :disabled="!hasSubjects" @click="openCreateDialog">
                <Plus class="w-4 h-4 mr-2" />
                新建标签
            </Button>
        </template>
    </PageHeader>
    <div class="flex flex-1 flex-col">
        <div class="@container/main flex flex-1 flex-col gap-4 px-4 py-6 md:flex-row">
            <!-- Desktop: category rail, stretches to match the table column's height -->
            <aside class="hidden shrink-0 rounded-md border p-2 md:block md:w-56 lg:w-64">
                <TagCategorySidebar
                    v-model:selected="selectedCategory"
                    v-model:editing-id="editingCategoryId"
                    v-model:editing-form="editingCategory"
                    v-model:is-adding="isAddingCategory"
                    v-model:new-category-form="newCategory"
                    :categories="tagCategories || []"
                    :disabled="!hasSubjects"
                    @create="createCategory"
                    @save-edit="saveCategory"
                    @delete="deleteCategory"
                    @create-tag="openCreateDialogForCategory"
                />
            </aside>

            <div class="flex min-w-0 flex-1 flex-col gap-4">
                <div class="flex items-center justify-between gap-2">
                    <!-- Mobile: category picker opens the same sidebar in a drawer -->
                    <div class="md:hidden">
                        <Sheet v-model:open="isMobileCategorySheetOpen">
                            <SheetTrigger as-child>
                                <Button variant="outline" class="justify-between">
                                    {{ currentCategoryLabel }}
                                    <ChevronDown class="ml-2 h-4 w-4 opacity-50" />
                                </Button>
                            </SheetTrigger>
                            <SheetContent side="left" class="w-72 p-4">
                                <SheetHeader class="p-0">
                                    <SheetTitle>标签分类</SheetTitle>
                                </SheetHeader>
                                <TagCategorySidebar
                                    class="mt-4"
                                    v-model:selected="selectedCategory"
                                    v-model:editing-id="editingCategoryId"
                                    v-model:editing-form="editingCategory"
                                    v-model:is-adding="isAddingCategory"
                                    v-model:new-category-form="newCategory"
                                    :categories="tagCategories || []"
                                    :disabled="!hasSubjects"
                                    @create="createCategory"
                                    @save-edit="saveCategory"
                                    @delete="deleteCategory"
                                    @create-tag="openCreateDialogForCategory"
                                />
                            </SheetContent>
                        </Sheet>
                    </div>
                    <h2 class="hidden text-sm font-medium text-muted-foreground md:block">
                        {{ currentCategoryLabel }}
                    </h2>
                    <span class="hidden text-sm text-muted-foreground md:block">共 {{ total }} 个标签</span>
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
                                        :checked="isAllPageSelected"
                                        @update:model-value="(v) => toggleAllPage(v as boolean)"
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
                            <TableRow v-for="tag in tags" :key="tag.id">
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
                                    <Badge variant="secondary">{{ categories.find(c => c.value === tag.category_id)?.label || '未分类' }}</Badge>
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
                            <TableRow v-if="tags.length === 0">
                                <TableCell colspan="5" class="text-center py-8 text-muted-foreground">
                                    暂无标签
                                </TableCell>
                            </TableRow>
                        </TableBody>
                    </Table>
                </div>

                <div v-if="total > 0" class="flex justify-center">
                    <Pagination v-model:page="page" :total="total" :sibling-count="1" show-edges :default-page="1"
                        :items-per-page="pageSize">
                        <PaginationContent v-slot="{ items }" class="flex items-center gap-1">
                            <PaginationPrevious class="h-8 w-8 p-0" aria-label="上一页">
                                <ChevronLeft class="h-4 w-4" />
                            </PaginationPrevious>
                            <template v-for="(item, index) in items">
                                <PaginationItem v-if="item.type === 'page'" :key="index" :value="item.value" as-child>
                                    <Button
                                        :variant="item.value === page ? 'outline' : 'ghost'"
                                        :class="[
                                            'w-8 h-8 p-0 text-sm',
                                            item.value === page ? 'border-primary text-primary font-medium' : 'text-muted-foreground'
                                        ]"
                                    >
                                        {{ item.value }}
                                    </Button>
                                </PaginationItem>
                                <PaginationEllipsis v-else :key="item.type" :index="index" class="size-8" />
                            </template>
                            <PaginationNext class="h-8 w-8 p-0" aria-label="下一页">
                                <ChevronRight class="h-4 w-4" />
                            </PaginationNext>
                        </PaginationContent>
                    </Pagination>
                </div>
            </div>

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
                            <Select v-model="categorySelectValue">
                                <SelectTrigger>
                                    <SelectValue placeholder="选择分类" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="none">未分类</SelectItem>
                                    <SelectItem v-for="cat in categories" :key="cat.value" :value="String(cat.value)">
                                        {{ cat.label }}
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                            <p class="text-xs text-muted-foreground">决定这个标签在筛选和选择时归到哪一组</p>
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
                        <Button :disabled="!currentTag.name?.trim()" @click="saveTag">保存</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <TagImportDialog v-model:open="isImportOpen" :subject-id="currentSubjectId" @imported="refresh(); refreshCategories()" />
        </div>
    </div>
</template>
