<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { ShoppingBasket } from '@lucide/vue'
import { useQuestionBasket } from '@/composables/useQuestionBasket'

defineEmits<{ click: [] }>()

const { count } = useQuestionBasket()
</script>

<template>
  <Button
    v-if="count > 0"
    size="icon"
    class="fixed bottom-24 right-6 z-40 h-12 w-12 rounded-full shadow-lg"
    title="试题篮"
    @click="$emit('click')"
  >
    <ShoppingBasket class="h-5 w-5" />
    <span
      class="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs font-medium text-destructive-foreground"
    >
      {{ count }}
    </span>
  </Button>
</template>
