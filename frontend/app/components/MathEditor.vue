<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import 'mathlive'
import 'mathlive/static.css'
import { Button } from '@/components/ui/button'
import { Keyboard } from 'lucide-vue-next'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits(['update:modelValue', 'confirm'])

const mathfieldRef = ref<HTMLElement | null>(null)
const keyboardContainerRef = ref<HTMLElement | null>(null)

const toggleKeyboard = () => {
  const mf = mathfieldRef.value as any
  if (mf) {
    mf.executeCommand('toggleVirtualKeyboard')
    setTimeout(() => mf.focus(), 50)
  }
}

onMounted(() => {
  const mf = mathfieldRef.value as any
  if (mf) {
    mf.value = props.modelValue
    
    mf.addEventListener('input', (evt: any) => {
      emit('update:modelValue', evt.target.value)
    })

    // Listen for Enter key to confirm
    mf.addEventListener('keydown', (evt: KeyboardEvent) => {
      if (evt.key === 'Enter' && !evt.shiftKey) {
        evt.preventDefault()
        emit('confirm')
      }
    })
    
    mf.virtualKeyboardMode = 'manual'
    mf.virtualKeyboardContainer = keyboardContainerRef.value

    mf.addEventListener('virtual-keyboard-toggle', () => {
      setTimeout(() => {
        mf.focus()
      }, 50)
    })

    // Auto focus
    setTimeout(() => {
      mf.focus()
    }, 50)
  }
})

watch(() => props.modelValue, (newVal) => {
  const mf = mathfieldRef.value as any
  if (mf && mf.value !== newVal) {
    mf.value = newVal
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex justify-end">
      <Button variant="outline" size="sm" @click="toggleKeyboard">
        <Keyboard class="w-4 h-4 mr-2" />
        虚拟键盘
      </Button>
    </div>

    <math-field 
      ref="mathfieldRef" 
      class="w-full p-2 rounded-md text-lg shadow-sm min-h-[60px] !border bg-background"
    >
      {{ modelValue }}
    </math-field>

    <div class="text-xs text-muted-foreground">
      提示：点击上方按钮可打开/关闭虚拟键盘。
    </div>

    <div ref="keyboardContainerRef"></div>
  </div>
</template>

<style scoped>
math-field {
  --keyboard-zindex: 3000;
  border-radius: 0.375rem;
  border: 1px solid hsl(var(--border));
  width: 100%;
  background: hsl(var(--background));
}
math-field::part(virtual-keyboard-toggle) {
  display: none;
}
math-field::part(menu-toggle) {
  display: none;
}
math-field:focus-within {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}
</style>
