<script setup lang="ts">
import QuestionGroupForm from '@/components/question-groups/QuestionGroupForm.vue'

const route = useRoute()
const groupId = Number(route.params.id)
</script>

<template><QuestionGroupForm :group-id="groupId" /></template>