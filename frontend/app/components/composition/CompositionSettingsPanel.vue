<script setup lang="ts">
// 统一外壳：把题号/赋分/显示三段设置合并为一张卡片，段落分隔由调用方用 Separator 插入。
</script>

<template>
  <div class="space-y-4 rounded-lg border bg-card p-4">
    <slot />
  </div>
</template>
