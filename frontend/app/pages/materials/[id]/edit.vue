<script setup lang="ts">
import StimulusForm from '@/components/stimuli/StimulusForm.vue'

// 需读取 add_question；未保存修改由离开确认保护，不靠缓存。
definePageMeta({ keepalive: false })

const route = useRoute()
const stimulusId = Number(route.params.id)
</script>

<template><StimulusForm :stimulus-id="stimulusId" /></template>