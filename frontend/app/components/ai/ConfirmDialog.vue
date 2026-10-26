<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

export type ConfirmResult = 'confirm' | 'alt' | 'cancel'

interface ConfirmOptions {
  title: string
  description?: string
  confirmLabel?: string
  altLabel?: string
  destructive?: boolean
}

const { t } = useI18n()

const open = ref(false)
const options = ref<ConfirmOptions>({ title: '' })
let resolver: ((r: ConfirmResult) => void) | null = null

const finish = (result: ConfirmResult) => {
  const r = resolver
  resolver = null
  open.value = false
  r?.(result)
}

const ask = (opts: ConfirmOptions): Promise<ConfirmResult> => {
  resolver?.('cancel')
  options.value = opts
  open.value = true
  return new Promise(resolve => { resolver = resolve })
}

watch(open, (v) => { if (!v && resolver) finish('cancel') })

defineExpose({ ask })
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ options.title }}</AlertDialogTitle>
        <AlertDialogDescription v-if="options.description" class="whitespace-pre-line">
          {{ options.description }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="finish('cancel')">{{ t('common.cancel') }}</AlertDialogCancel>
        <Button v-if="options.altLabel" variant="outline" @click="finish('alt')">{{ options.altLabel }}</Button>
        <Button :variant="options.destructive ? 'destructive' : 'default'" @click="finish('confirm')">
          {{ options.confirmLabel ?? t('common.confirm') }}
        </Button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
