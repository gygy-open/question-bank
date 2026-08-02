<script setup lang="ts">
import { ref } from 'vue'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GripVertical, Eye, X, Heading, Check } from 'lucide-vue-next'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import type { PaperItem } from '~/types'

const props = defineProps<{
  item: PaperItem
  index: number
}>()

const emit = defineEmits<{
  remove: []
  'view-detail': []
  'update-section': [value: string | null]
}>()

const typeLabels: Record<string, string> = {
  single_choice: '单选',
  multiple_choice: '多选',
  true_false: '判断',
  fill_in_the_blank: '填空',
  free_response: '解答',
}

const editingSection = ref(false)
const sectionDraft = ref('')

const startEditSection = () => {
  sectionDraft.value = props.item.section_title || ''
  editingSection.value = true
}

const commitSection = () => {
  const value = sectionDraft.value.trim()
  editingSection.value = false
  if (value === (props.item.section_title || '')) return
  emit('update-section', value || null)
}

const clearSection = () => {
  editingSection.value = false
  emit('update-section', null)
}
</script>

<template>
  <div class="space-y-2">
    <!-- 大题标题 -->
    <div v-if="editingSection" class="flex items-center gap-2 pl-11">
      <Input
        v-model="sectionDraft"
        placeholder="大题标题，如 一、选择题"
        class="h-8"
        autofocus
        @keydown.enter="commitSection"
        @keydown.esc="editingSection = false"
      />
      <Button variant="ghost" size="icon" class="h-8 w-8" title="确定" @click="commitSection">
        <Check class="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" class="h-8 w-8 text-destructive" title="移除标题" @click="clearSection">
        <X class="h-4 w-4" />
      </Button>
    </div>
    <div
      v-else-if="item.section_title"
      class="pl-11 flex items-center gap-2 group/section"
    >
      <h3
        class="text-base font-semibold cursor-pointer hover:text-primary"
        title="点击编辑大题标题"
        @click="startEditSection"
      >
        {{ item.section_title }}
      </h3>
    </div>

    <Card class="group hover:border-primary/50 transition-colors">
      <CardContent class="p-3">
        <div class="flex items-start gap-3">
          <div class="drag-handle cursor-move opacity-40 group-hover:opacity-100 transition-opacity pt-1">
            <GripVertical class="h-5 w-5 text-muted-foreground" />
          </div>

          <div class="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-medium">
            {{ index + 1 }}
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-2">
              <Badge v-if="item.question" variant="outline">
                {{ typeLabels[item.question.q_type] || item.question.q_type }}
              </Badge>
              <Badge v-if="item.question" variant="secondary">
                难度 {{ item.question.difficulty }}
              </Badge>
            </div>
            <div class="text-sm max-w-none line-clamp-2 text-muted-foreground">
              <MarkdownPreview v-if="item.question" :content="item.question.content" />
              <span v-else>题目已删除</span>
            </div>
          </div>

          <div class="flex-shrink-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              :title="item.section_title ? '编辑大题标题' : '在此题前加大题标题'"
              @click="startEditSection"
            >
              <Heading class="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" class="h-8 w-8" title="查看题目" @click="emit('view-detail')">
              <Eye class="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-destructive hover:text-destructive"
              title="移除"
              @click="emit('remove')"
            >
              <X class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
