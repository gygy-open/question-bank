<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'

defineProps<{
  title: string
}>()

const router = useRouter()
</script>

<template>
  <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
    <SidebarTrigger class="-ml-1" />
      <Separator
        orientation="vertical"
        class="mx-2 data-[orientation=vertical]:h-4"
      />
      <h1 class="text-base font-medium">
        {{ title }}
      </h1>
      <div class="ml-auto flex items-center gap-2">
        <slot name="actions" />
      </div>
  </header>
</template>