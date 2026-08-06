<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <main
    data-slot="sidebar-inset"
    :class="cn(
      'bg-zinc-50 relative flex w-full flex-1 flex-col',
      props.class,
    )"
  >
    <slot />
  </main>
</template>
