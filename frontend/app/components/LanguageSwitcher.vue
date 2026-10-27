<script setup lang="ts">
import { Check, Languages } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const { locale, locales, setLocale, t } = useI18n()
// 显示当前语言的自称（简体中文 / English），读不懂当前界面的人也能认出它是语言入口。
const currentName = computed(() => locales.value.find(l => l.code === locale.value)?.name ?? locale.value)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="sm" class="gap-1.5 text-muted-foreground" :aria-label="t('language.switch')" :title="t('language.switch')">
        <Languages class="size-4" />
        <span>{{ currentName }}</span>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem v-for="l in locales" :key="l.code" @click="setLocale(l.code)">
        <Check class="mr-2 size-4" :class="l.code === locale ? 'opacity-100' : 'opacity-0'" />
        {{ l.name }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
