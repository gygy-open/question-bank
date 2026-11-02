<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
import { getSubjectColor, getSubjectIcon, getSubjectInitial } from '@/lib/subjectAvatar'

const props = withDefaults(defineProps<{
  id: number
  name: string
  size?: 'sm' | 'md'
  class?: HTMLAttributes['class']
}>(), { size: 'md' })

const icon = computed(() => getSubjectIcon(props.name))
</script>

<template>
  <div
    :class="cn(
      'flex shrink-0 items-center justify-center font-semibold text-white',
      size === 'md' ? 'size-8 rounded-lg text-xs' : 'size-5 rounded-md text-[9px]',
      getSubjectColor(id),
      props.class,
    )"
    aria-hidden="true"
  >
    <component :is="icon" v-if="icon" :class="size === 'md' ? 'size-4.5' : 'size-3'" />
    <span v-else>{{ getSubjectInitial(name) }}</span>
  </div>
</template>
