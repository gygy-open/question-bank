<script setup lang="ts">
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Sparkles, ArrowRight } from '@lucide/vue'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import type { Subject } from '~/types'

definePageMeta({
  layout: 'empty',
})

const { $api } = useNuxtApp()
const { refreshSubjects, setSubject, init, hasSubjects } = useSubjectContext()

const name = ref('')
const slug = ref('')
const description = ref('')
const slugTouched = ref(false)
const submitting = ref(false)

// 从名称生成 slug 建议（中文等非拉丁字符会被清空，此时需用户手填）
const suggestSlug = (v: string) =>
  v.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')

watch(name, (v) => {
  if (!slugTouched.value) slug.value = suggestSlug(v)
})

// 已经有科目则不该停留在引导页
onMounted(async () => {
  await init()
  if (hasSubjects.value) await navigateTo('/')
})

const submit = async () => {
  if (!name.value.trim()) {
    toast.error('请输入科目名称')
    return
  }
  if (!slug.value.trim()) {
    toast.error('请输入科目标识 (slug)')
    return
  }
  submitting.value = true
  try {
    const created = await $api<Subject>('/subjects', {
      method: 'POST',
      body: {
        name: name.value.trim(),
        slug: slug.value.trim(),
        description: description.value.trim() || undefined,
        required_review_count: 1,
      },
    })
    await refreshSubjects()
    await setSubject(created.id)
    toast.success('科目已创建，开始使用吧')
    await navigateTo('/')
  } catch (e: any) {
    toast.error(e?.data?.detail || '创建失败，请重试')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen w-full items-center justify-center bg-muted/40 px-4 py-8">
    <Card class="w-full sm:w-[520px]">
      <CardHeader class="space-y-1">
        <div class="flex justify-center mb-2">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Sparkles class="h-7 w-7" />
          </div>
        </div>
        <CardTitle class="text-2xl text-center">创建你的第一个科目</CardTitle>
        <CardDescription class="text-center">
          题库以科目为单位组织。先创建一个科目，之后可随时在「科目管理」中增删。
        </CardDescription>
      </CardHeader>

      <CardContent class="grid gap-4">
        <div class="grid gap-1.5">
          <Label>科目名称</Label>
          <Input v-model="name" placeholder="例如：高中数学" @keyup.enter="submit" />
        </div>

        <div class="grid gap-1.5">
          <Label>标识 (Slug)</Label>
          <Input
            v-model="slug"
            placeholder="例如：math"
            @input="slugTouched = true"
            @keyup.enter="submit"
          />
          <p class="text-xs text-muted-foreground">
            用于 URL 与系统内部标识，建议使用英文小写；名称为中文时请手动填写。
          </p>
        </div>

        <div class="grid gap-1.5">
          <Label>描述<span class="text-muted-foreground font-normal">（可选）</span></Label>
          <Input v-model="description" placeholder="可选：科目的简要说明" @keyup.enter="submit" />
        </div>
      </CardContent>

      <CardFooter>
        <Button class="w-full" :disabled="submitting" @click="submit">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          <template v-else>
            开始使用
            <ArrowRight class="ml-2 h-4 w-4" />
          </template>
        </Button>
      </CardFooter>
    </Card>
  </div>
</template>
