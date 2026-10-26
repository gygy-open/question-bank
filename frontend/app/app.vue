<script setup lang="ts">
import { Toaster } from '~/components/ui/sonner'

const { locale, t } = useI18n()
const { appName } = useRuntimeConfig().public
useHead({
  htmlAttrs: { lang: locale },
  title: computed(() => `${appName} - ${t('app.slogan')}`),
})
</script>

<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <Toaster />
  </div>
</template>
