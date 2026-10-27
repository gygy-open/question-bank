<script setup lang="ts">
// AI 助手形象：取自 logo 的开放圆环作为脸，缺口处的对勾换成星芒。
// 使用 currentColor，尺寸/颜色由外部 class 控制。
withDefaults(defineProps<{ thinking?: boolean }>(), { thinking: false })
</script>

<template>
  <svg viewBox="11 3 90 90" fill="none" aria-hidden="true" :data-thinking="thinking ? '' : undefined" class="group/mascot">
    <path
      d="M78 35C72 26 62 20 50 20C33.4315 20 20 33.4315 20 50C20 66.5685 33.4315 80 50 80C60.5 80 69.5 74 74.5 65"
      stroke="currentColor"
      stroke-width="10"
      stroke-linecap="round"
      opacity="0.45"
    />
    <g
      class="origin-center [transform-box:fill-box] motion-safe:animate-mascot-blink motion-safe:group-data-thinking/mascot:animate-mascot-glance"
      fill="currentColor"
    >
      <rect x="35" y="41" width="10" height="17" rx="5" />
      <rect x="54" y="41" width="10" height="17" rx="5" />
    </g>
    <path
      class="origin-center [transform-box:fill-box] motion-safe:group-data-thinking/mascot:animate-mascot-twinkle"
      d="M83 10C84.6 18.5 87.5 21.4 96 23C87.5 24.6 84.6 27.5 83 36C81.4 27.5 78.5 24.6 70 23C78.5 21.4 81.4 18.5 83 10Z"
      fill="currentColor"
    />
  </svg>
</template>
