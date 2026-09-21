<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { BookOpen } from '@lucide/vue'
import type { Question, QuestionRelations } from '@/types'
import RichContent from './rich-editor/RichContent.vue'

const props = defineProps<{
  open: boolean
  questionId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const { $api } = useNuxtApp()
const loading = ref(false)
const question = ref<Question | null>(null)
const relations = ref<QuestionRelations | null>(null)

const fetchQuestion = async (id: number) => {
  loading.value = true
  try {
    const [questionResponse, relationsResponse] = await Promise.all([
      $api<Question>(`/questions/${id}`),
      $api<QuestionRelations>(`/questions/${id}/relations`),
    ])
    question.value = questionResponse
    relations.value = relationsResponse
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

watch(() => props.questionId, (newId) => {
  if (newId && props.open) {
    fetchQuestion(newId)
  }
})

watch(() => props.open, (isOpen) => {
  if (isOpen && props.questionId) {
    fetchQuestion(props.questionId)
  }
})

const isOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})
</script>

<template>
  <Sheet v-model:open="isOpen">
    <SheetContent class="w-[600px] sm:w-[800px] overflow-y-auto">
      <SheetHeader>
        <SheetTitle>题目派生关系</SheetTitle>
        <SheetDescription>
          查看来源题、派生题及涉及的知识点
        </SheetDescription>
      </SheetHeader>
      
      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>
      
      <div v-else-if="question" class="mt-6 space-y-6 px-4">
        <!-- Source Questions -->
        <div v-for="source in relations?.sources" :key="source.relation_id" class="relative">
          <div class="border rounded-lg p-4 bg-muted/40 border-dashed relative z-10">
            <div class="flex items-center gap-2 mb-2">
              <Badge variant="outline" class="bg-background">来源题</Badge>
              <span class="text-sm text-muted-foreground">ID: {{ source.question.id }}</span>
              <Button variant="link" size="sm" class="h-auto p-0 ml-auto text-xs" @click="fetchQuestion(source.question.id)">
                查看此题
              </Button>
            </div>
            <RichContent :content="source.question.content" class="text-sm opacity-80" />
          </div>
        </div>

        <!-- Current Question -->
        <div class="relative">
          <div class="border rounded-lg p-4 bg-card shadow-sm relative z-10 ring-2 ring-primary/10">
            <div class="flex items-center gap-2 mb-2">
              <Badge variant="default">当前题目</Badge>
              <span class="text-sm text-muted-foreground">ID: {{ question.id }}</span>
            </div>
            <RichContent :content="question.content" class="text-sm" />
            
            <!-- Knowledge Points -->
            <div v-if="question.knowledge_points?.length" class="mt-3 flex flex-wrap gap-2">
              <Badge v-for="kp in question.knowledge_points" :key="kp.id" variant="outline" class="text-xs">
                <BookOpen class="w-3 h-3 mr-1" />
                {{ kp.name }}
              </Badge>
            </div>
          </div>

          <!-- Derived Questions -->
          <div v-if="relations?.targets.length" class="mt-6 space-y-6 pl-8">
            <div v-for="target in relations.targets" :key="target.relation_id" class="relative">
              <div class="border rounded-lg p-4 bg-muted/30">
                <div class="flex items-center gap-2 mb-2">
                  <Badge variant="outline">派生题</Badge>
                  <span class="text-sm text-muted-foreground">ID: {{ target.question.id }}</span>
                  <Button variant="link" size="sm" class="h-auto p-0 ml-auto text-xs" @click="fetchQuestion(target.question.id)">
                    查看此题
                  </Button>
                </div>
                <RichContent :content="target.question.content" class="text-sm" />
                
                <div v-if="target.question.knowledge_points?.length" class="mt-3 flex flex-wrap gap-2">
                  <Badge v-for="kp in target.question.knowledge_points" :key="kp.id" variant="outline" class="text-xs">
                    <BookOpen class="w-3 h-3 mr-1" />
                    {{ kp.name }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
          
          <div v-else class="mt-4 text-sm text-muted-foreground italic pl-4">
            暂无派生题
          </div>
        </div>
      </div>
    </SheetContent>
  </Sheet>
</template>
