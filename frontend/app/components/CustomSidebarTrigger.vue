<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { ChevronsLeft, ChevronsRight } from "@lucide/vue"
import { cn } from "@/lib/utils"
import { Button } from '@/components/ui/button'
import { useSidebar } from "@/components/ui/sidebar"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()

const { state, toggleSidebar } = useSidebar()
</script>

<template>
  <Button
    data-sidebar="trigger"
    data-slot="sidebar-trigger"
    variant="ghost"
    size="icon"
    :class="cn('h-7 w-7 text-muted-foreground hover:text-foreground', props.class)"
    @click="toggleSidebar"
  >
    <ChevronsLeft v-if="state === 'expanded'" class="size-5" />
    <ChevronsRight v-else class="size-5" />
    <span class="sr-only">Toggle Sidebar</span>
  </Button>
</template>
