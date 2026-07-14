<script setup lang="ts">
import type MarkdownPreviewVue from '~/components/MarkdownPreview.vue';

definePageMeta({
  layout: false
})

const content = ref<string>('')

</script>

<template>
  <div class="p-6 flex gap-4">
    <TiptapEditor v-model="content" class="flex-1" />
    <div class="border p-4 flex-1">
      <MarkdownPreview :content="content" />
    </div>
  </div>
</template>