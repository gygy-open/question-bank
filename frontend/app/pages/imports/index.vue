<script setup lang="ts">
import { Inbox, Plus } from '@lucide/vue'
import { Button } from '@/components/ui/button'

const { t } = useI18n()
</script>

<template>
  <div class="flex h-full min-h-[60svh] flex-col items-center justify-center gap-4 p-8 text-center">
    <div class="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
      <Inbox class="h-7 w-7 text-muted-foreground" />
    </div>
    <div class="max-w-sm space-y-1">
      <h2 class="text-lg font-semibold">{{ t('imports.empty.title') }}</h2>
      <p class="text-sm text-muted-foreground">{{ t('imports.empty.description') }}</p>
    </div>
    <Button as-child>
      <NuxtLink to="/imports?new=1"><Plus class="mr-1.5 h-4 w-4" />{{ t('imports.new') }}</NuxtLink>
    </Button>
  </div>
</template>
