<script setup lang="ts">
import MaterialForm from '@/components/materials/MaterialForm.vue'

const route = useRoute()
const materialId = Number(route.params.id)
</script>

<template><MaterialForm :material-id="materialId" /></template>