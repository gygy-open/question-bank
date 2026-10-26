<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { SetupStatus } from '@/types'

definePageMeta({
  layout: 'empty'
})

const { t } = useI18n()
const { login } = useAuth()
const router = useRouter()
const { $api } = useNuxtApp()

const isLoading = ref(false)
const registrationEnabled = ref(false)

// 若系统尚未完成首次初始化，引导至安装向导
onMounted(async () => {
  try {
    const res = await $api<SetupStatus>('/setup/status')
    if (!res.db_configured || !res.admin_initialized) {
      router.replace('/setup')
    }
  } catch {
    // 忽略状态探测失败
  }
  try {
    const cfg = await $api<{ enabled: boolean }>('/register/config')
    registrationEnabled.value = cfg.enabled
  } catch {
    // 忽略注册配置探测失败
  }
})

// schema 放在 computed 里，切换语言后校验文案随之更新（页面会被 keepalive 缓存）。
const formSchema = computed(() => toTypedSchema(z.object({
  username: z.string({ required_error: t('auth.login.usernameRequired') }).min(1, t('auth.login.usernameRequired')),
  password: z.string({ required_error: t('auth.login.passwordRequired') }).min(1, t('auth.login.passwordRequired')),
})))

const form = useForm({
  validationSchema: formSchema,
})

const onSubmit = form.handleSubmit(async (values) => {
  isLoading.value = true
  try {
    await login({ username: values.username, password: values.password })
    toast.success(t('auth.login.success'))
    router.push('/')
  } catch (error: any) {
    const status = error.statusCode ?? error.status ?? error.response?.status
    if (status === 403) {
      toast.error(t('auth.login.inactive'))
    } else if (status === 400) {
      toast.error(t('auth.login.invalidCredentials'))
    } else {
      toast.error(error.message || t('auth.login.failed'))
    }
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <div class="relative flex h-screen w-full items-center justify-center bg-muted/40 px-4">
    <LanguageSwitcher class="absolute right-4 top-4" />
    <Card class="w-full sm:w-[400px]">
      <CardHeader class="space-y-1">
        <div class="flex justify-center mb-4">
          <img src="/logo.svg" alt="Logo" class="h-16 w-auto" />
        </div>
        <CardTitle class="text-2xl text-center">{{ t('auth.login.title') }}</CardTitle>
        <CardDescription class="text-center">
          {{ t('auth.login.description') }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit="onSubmit">
          <div class="grid gap-4">
            <FormField v-slot="{ componentField }" name="username">
              <FormItem>
                <FormLabel>{{ t('auth.login.username') }}</FormLabel>
                <FormControl>
                  <Input type="text" placeholder="admin" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
            
            <FormField v-slot="{ componentField }" name="password">
              <FormItem>
                <FormLabel>{{ t('auth.login.password') }}</FormLabel>
                <FormControl>
                  <Input type="password" placeholder="******" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
            
            <Button type="submit" :disabled="isLoading" class="w-full">
              <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
              {{ t('auth.login.submit') }}
            </Button>

            <div v-if="registrationEnabled" class="text-center text-sm text-muted-foreground">
              {{ t('auth.login.noAccount') }}
              <NuxtLink to="/register" class="text-primary hover:underline">{{ t('auth.login.register') }}</NuxtLink>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
