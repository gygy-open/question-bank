<script setup lang="ts">
import AiPanelToggle from '~/components/chat/AiPanelToggle.vue'
import { ArrowLeft } from '@lucide/vue'

defineProps<{
  title: string
}>()

const router = useRouter()
</script>

<template>
  <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
    <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>{{ title }}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
    <div class="ml-auto flex items-center gap-2">
      <slot name="actions" />
      <AiPanelToggle />
    </div>
  </header>
</template>