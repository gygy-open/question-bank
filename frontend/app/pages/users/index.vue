<script setup lang="ts">
import UserManager from '~/components/manager/UserManager.vue'
import PageHeader from '~/components/PageHeader.vue'

definePageMeta({
  middleware: ['admin']
})
</script>

<template>
  <PageHeader title="用户管理" />
  <div class="flex flex-1 flex-col p-4">
    <UserManager />
  </div>
</template>
