<script setup lang="ts">
import StimulusForm from '@/components/stimuli/StimulusForm.vue'

const route = useRoute()
const stimulusId = Number(route.params.id)
</script>

<template><StimulusForm :stimulus-id="stimulusId" /></template>