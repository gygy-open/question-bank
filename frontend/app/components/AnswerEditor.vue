<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Plus, Trash2, X } from 'lucide-vue-next'
import TiptapEditor from './TiptapEditor.vue'

interface Props {
  modelValue: any
  qType: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: any): void
}>()

const internalAnswer = ref<any>(null)

const initInternalAnswer = () => {
  if (props.qType === 'fill_in_the_blank') {
    let parsed = props.modelValue
    if (typeof parsed === 'string') {
      try {
        if (parsed.trim().startsWith('[')) {
          parsed = JSON.parse(parsed)
        }
      } catch (e) {
        // ignore
      }
    }

    if (Array.isArray(parsed) && parsed.length > 0) {
       internalAnswer.value = parsed.map((item: any) => {
           if (Array.isArray(item)) return item.map(String)
           return [String(item)]
       })
    } else {
       internalAnswer.value = [['']]
    }
  } else {
    internalAnswer.value = props.modelValue
  }
}

watch(() => props.modelValue, (newVal) => {
    if (props.qType === 'fill_in_the_blank') {
        if (JSON.stringify(newVal) !== JSON.stringify(internalAnswer.value)) {
             initInternalAnswer()
        }
    } else {
        if (newVal !== internalAnswer.value) {
            internalAnswer.value = newVal
        }
    }
}, { immediate: true })

watch(() => props.qType, (newType, oldType) => {
    if (newType === oldType) return
    
    if (newType === 'fill_in_the_blank') {
        let preserved = false
        try {
            let current = internalAnswer.value
             if (typeof current === 'string' && current.trim().startsWith('[')) {
                 current = JSON.parse(current)
             }
             
             if (Array.isArray(current) && current.length > 0) {
                 internalAnswer.value = current.map((item: any) => {
                     if (Array.isArray(item)) return item.map(String)
                     return [String(item)]
                 })
                 preserved = true
             }
        } catch(e) {}
        
        if (!preserved) {
            internalAnswer.value = [['']]
        }
    } else {
        if (Array.isArray(internalAnswer.value)) {
            internalAnswer.value = ''
        }
    }
})

watch(internalAnswer, (newVal) => {
    emit('update:modelValue', newVal)
}, { deep: true })

const addBlank = () => {
  if (!Array.isArray(internalAnswer.value)) {
    internalAnswer.value = []
  }
  internalAnswer.value.push([''])
}

const removeBlank = (index: number) => {
  if (!Array.isArray(internalAnswer.value)) return
  internalAnswer.value.splice(index, 1)
}

const addBlankAnswer = (blankIndex: number) => {
  if (!Array.isArray(internalAnswer.value)) return
  internalAnswer.value[blankIndex].push('')
}

const removeBlankAnswer = (blankIndex: number, answerIndex: number) => {
  if (!Array.isArray(internalAnswer.value)) return
  internalAnswer.value[blankIndex].splice(answerIndex, 1)
}
</script>

<template>
  <div class="space-y-2">
    <Label>答案</Label>
    <div v-if="qType === 'fill_in_the_blank'">
      <div class="space-y-4">
        <div v-for="(blank, bIndex) in internalAnswer" :key="bIndex" class="p-4 border rounded-md bg-muted/30">
          <div class="flex items-center justify-between mb-2">
            <Label class="text-sm font-medium">第 {{ bIndex + 1 }} 空 (允许的答案)</Label>
            <Button variant="ghost" size="icon" class="h-6 w-6" @click="removeBlank(bIndex)" :disabled="internalAnswer.length <= 1">
              <Trash2 class="h-3 w-3" />
            </Button>
          </div>
          <div class="space-y-2">
            <div v-for="(ans, aIndex) in blank" :key="aIndex" class="flex gap-2 items-start">
              <div class="flex-1">
                <TiptapEditor
                  v-model="internalAnswer[bIndex][aIndex]"
                  placeholder="输入参考答案..."
                  min-height="min-h-[60px]"
                />
              </div>
              <Button variant="ghost" size="icon" class="h-9 w-9 shrink-0 mt-0.5" @click="removeBlankAnswer(bIndex, aIndex)" :disabled="blank.length <= 1">
                <X class="h-4 w-4" />
              </Button>
            </div>
            <Button variant="outline" size="sm" class="w-full border-dashed h-8" @click="addBlankAnswer(bIndex)">
              <Plus class="h-3 w-3 mr-1" /> 添加备选答案
            </Button>
          </div>
        </div>
        <Button variant="outline" class="w-full border-dashed" @click="addBlank">
          <Plus class="h-4 w-4 mr-2" /> 添加填空项
        </Button>
      </div>
    </div>
    <div v-else>
      <TiptapEditor v-model="internalAnswer" />
    </div>
  </div>
</template>