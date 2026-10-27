<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { ShoppingBasket } from '@lucide/vue'
import { useQuestionBasket } from '@/composables/useQuestionBasket'

const { t } = useI18n()

defineEmits<{ click: [] }>()

const { count } = useQuestionBasket()
</script>

<template>
  <Button
    variant="outline"
    size="sm"
    class="gap-1.5"
    :title="t('basket.title')"
    @click="$emit('click')"
  >
    <ShoppingBasket class="h-4 w-4" />
    <span class="hidden sm:inline">{{ t('basket.title') }}</span>
    <span
      v-if="count > 0"
      class="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs font-medium text-primary-foreground"
    >
      {{ count }}
    </span>
  </Button>
</template>
