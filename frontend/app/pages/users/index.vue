<script setup lang="ts">
import UserManager from '~/components/manager/UserManager.vue'
import PageHeader from '~/components/PageHeader.vue'

const { t } = useI18n()

definePageMeta({
  middleware: ['admin']
})
</script>

<template>
  <PageHeader :title="t('nav.users')" />
  <div class="flex flex-1 flex-col p-4">
    <UserManager />
  </div>
</template>
