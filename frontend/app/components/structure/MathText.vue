<script setup lang="ts">
/**
 * 渲染一段可能含 `$...$` / `$$...$$` 公式的纯文本(拆解快照里的题干、条件、设问)。
 *
 * 文字原样输出(自动转义),公式交给 KaTeX;公式写错时显示原始 LaTeX,不抛错。
 */
import { computed } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { splitMath } from '@/lib/structure'

const props = defineProps<{
  /** 待渲染的文本。 */
  text: string
}>()

// 拆成文字 / 公式片段;公式预先渲染成 HTML,模板里只做拼接。
const parts = computed(() =>
  splitMath(props.text || '').map((part) => {
    if (!part.math) return { ...part, html: '' }
    try {
      return { ...part, html: katex.renderToString(part.value, { throwOnError: false, displayMode: part.display }) }
    } catch {
      return { ...part, math: false, value: part.display ? `$$${part.value}$$` : `$${part.value}$`, html: '' }
    }
  }),
)
</script>

<template>
  <span class="whitespace-pre-wrap break-words">
    <template v-for="(part, index) in parts" :key="index">
      <!-- eslint-disable-next-line vue/no-v-html -- KaTeX 输出,输入已由 KaTeX 转义 -->
      <span v-if="part.math" v-html="part.html" />
      <template v-else>{{ part.value }}</template>
    </template>
  </span>
</template>
