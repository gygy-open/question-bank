<script setup lang="ts">
definePageMeta({
  layout: false
})

import RichEditor from '~/components/rich-editor/RichEditor.vue';
import { renderRichContentToHTML } from '~/components/rich-editor/renderRichContent';

const schema = ref('')
</script>

<template>
  <div class="p-6 flex gap-4">
    <RichEditor v-model="schema"  />
  </div>
  <Card class="p-4">
    <pre class="text-xs whitespace-pre-wrap">{{ schema }}</pre>
  </Card>
  <Card class="p-4 mt-4">
    <div class="prose prose-sm dark:prose-invert max-w-none" v-html="renderRichContentToHTML(schema)" />
  </Card>
</template>