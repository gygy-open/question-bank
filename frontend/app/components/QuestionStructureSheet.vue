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
import { BookOpen } from 'lucide-vue-next'
import type { Question } from '@/types'
import MarkdownPreview from './MarkdownPreview.vue'

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

const fetchQuestion = async (id: number) => {
  loading.value = true
  try {
    question.value = await $api<Question>(`/questions/${id}`)
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
        <SheetTitle>题目结构图谱</SheetTitle>
        <SheetDescription>
          查看题目拆解关系及涉及的知识点
        </SheetDescription>
      </SheetHeader>
      
      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>
      
      <div v-else-if="question" class="mt-6 space-y-6 px-4">
        <!-- Parent Question -->
        <div v-if="question.parent" class="relative">
          <!-- Vertical line connecting to current question -->
          <div class="absolute left-4 top-8 bottom-[-24px] w-px bg-border"></div>
          
          <div class="border rounded-lg p-4 bg-muted/40 border-dashed relative z-10">
            <div class="flex items-center gap-2 mb-2">
              <Badge variant="outline" class="bg-background">母题</Badge>
              <span class="text-sm text-muted-foreground">ID: {{ question.parent.id }}</span>
              <Button variant="link" size="sm" class="h-auto p-0 ml-auto text-xs" @click="fetchQuestion(question.parent!.id)">
                查看此题
              </Button>
            </div>
            <MarkdownPreview :content="question.parent.content" class="text-sm opacity-80" />
          </div>
        </div>

        <!-- Current Question -->
        <div class="relative" :class="{ 'pl-8': question.parent }">
          <!-- Connector from parent -->
          <div v-if="question.parent" class="absolute left-0 top-1/2 w-8 h-px bg-border -translate-y-1/2 hidden"></div> <!-- Simplified vertical flow instead -->
          
          <div class="absolute left-4 top-8 bottom-0 w-px bg-border" v-if="question.children?.length"></div>
          
          <div class="border rounded-lg p-4 bg-card shadow-sm relative z-10 ring-2 ring-primary/10">
            <div class="flex items-center gap-2 mb-2">
              <Badge variant="default">当前题目</Badge>
              <span class="text-sm text-muted-foreground">ID: {{ question.id }}</span>
            </div>
            <MarkdownPreview :content="question.content" class="text-sm" />
            
            <!-- Knowledge Points -->
            <div v-if="question.knowledge_points?.length" class="mt-3 flex flex-wrap gap-2">
              <Badge v-for="kp in question.knowledge_points" :key="kp.id" variant="outline" class="text-xs">
                <BookOpen class="w-3 h-3 mr-1" />
                {{ kp.name }}
              </Badge>
            </div>
          </div>

          <!-- Children -->
          <div v-if="question.children?.length" class="mt-6 space-y-6 pl-8">
            <div v-for="(child, index) in question.children" :key="child.id" class="relative">
              <!-- Connector -->
              <div class="absolute -left-8 top-6 w-8 h-px bg-border"></div>
              <div class="absolute -left-8 top-6 w-2 h-2 rounded-full bg-border -translate-x-1/2"></div>
              
              <div class="border rounded-lg p-4 bg-muted/30">
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-sm text-muted-foreground">ID: {{ child.id }}</span>
                </div>
                <MarkdownPreview :content="child.content" class="text-sm" />
                
                <!-- Child Knowledge Points -->
                <div v-if="child.knowledge_points?.length" class="mt-3 flex flex-wrap gap-2">
                  <Badge v-for="kp in child.knowledge_points" :key="kp.id" variant="outline" class="text-xs">
                    <BookOpen class="w-3 h-3 mr-1" />
                    {{ kp.name }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
          
          <div v-else class="mt-4 text-sm text-muted-foreground italic pl-4">
            暂无拆解步骤
          </div>
        </div>
      </div>
    </SheetContent>
  </Sheet>
</template>
