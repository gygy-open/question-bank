<script setup lang="ts">
import StimulusForm from '@/components/stimuli/StimulusForm.vue'

// 每次进入都是一份新草稿，并需读取 from_question。
definePageMeta({ keepalive: false })
</script>

<template><StimulusForm /></template>