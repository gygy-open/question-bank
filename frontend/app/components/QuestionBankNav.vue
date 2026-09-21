<script setup lang="ts">
const route = useRoute()

const items = [
  { label: '题目', to: '/questions' },
  { label: '题组', to: '/question-groups' },
  { label: '材料', to: '/materials' },
]

const isActive = (to: string) => route.path === to || route.path.startsWith(`${to}/`)
</script>

<template>
  <nav aria-label="题库分类" class="border-b px-4">
    <div class="grid h-11 w-full grid-cols-3 sm:flex sm:w-auto sm:gap-6">
      <NuxtLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        :aria-current="isActive(item.to) ? 'page' : undefined"
        class="relative flex min-w-0 items-center justify-center px-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground sm:px-1"
        :class="isActive(item.to) ? 'text-foreground after:absolute after:inset-x-1 after:bottom-0 after:h-0.5 after:bg-primary sm:after:inset-x-0' : ''"
      >
        {{ item.label }}
      </NuxtLink>
    </div>
  </nav>
</template>