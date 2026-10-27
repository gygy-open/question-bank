<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { Eye, EyeOff, Loader2, X } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { SetupStatus } from '@/types'

definePageMeta({
  layout: 'empty'
})

const { t } = useI18n()
const { login } = useAuth()
const router = useRouter()
const { $api } = useNuxtApp()

const appName = useRuntimeConfig().public.appName as string

const isLoading = ref(false)
const registrationEnabled = ref(false)
const showPassword = ref(false)
const version = ref('')
const usernameWrap = ref<HTMLElement | null>(null)
const passwordWrap = ref<HTMLElement | null>(null)

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
  try {
    const info = await $api<{ version: string }>('/system/version')
    version.value = info.version
  } catch {
    // 版本号仅作展示，失败时不显示
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

function clearField(name: 'username' | 'password', wrap: HTMLElement | null) {
  form.setFieldValue(name, '', false)
  wrap?.querySelector('input')?.focus()
}

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
  <div class="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-muted/40 px-4">
    <div class="pointer-events-none absolute inset-0 bg-radial-[at_50%_0%] from-primary/10 to-transparent to-60%" />

    <Card class="relative w-full sm:w-[400px]">
      <CardHeader class="space-y-1">
        <div class="flex justify-center mb-4">
          <img src="/logo.svg" alt="Logo" class="h-16 w-auto" />
        </div>
        <CardTitle class="text-2xl text-center">{{ appName }}</CardTitle>
        <CardDescription class="text-center">
          {{ t('app.slogan') }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit="onSubmit">
          <div class="grid gap-4">
            <FormField v-slot="{ componentField, value }" name="username">
              <FormItem>
                <FormLabel>{{ t('auth.login.username') }}</FormLabel>
                <div ref="usernameWrap" class="relative">
                  <FormControl>
                    <Input type="text" placeholder="admin" autocomplete="username" class="pr-9" v-bind="componentField" />
                  </FormControl>
                  <button
                    v-if="value"
                    type="button"
                    tabindex="-1"
                    class="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                    :aria-label="t('auth.login.clearUsername')"
                    :title="t('auth.login.clearUsername')"
                    @click="clearField('username', usernameWrap)"
                  >
                    <X class="h-4 w-4" />
                  </button>
                </div>
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ componentField, value }" name="password">
              <FormItem>
                <FormLabel>{{ t('auth.login.password') }}</FormLabel>
                <div ref="passwordWrap" class="relative">
                  <FormControl>
                    <Input
                      :type="showPassword ? 'text' : 'password'"
                      placeholder="******"
                      autocomplete="current-password"
                      :class="value ? 'pr-16' : 'pr-9'"
                      v-bind="componentField"
                    />
                  </FormControl>
                  <div class="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                    <button
                      v-if="value"
                      type="button"
                      tabindex="-1"
                      class="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                      :aria-label="t('auth.login.clearPassword')"
                      :title="t('auth.login.clearPassword')"
                      @click="clearField('password', passwordWrap)"
                    >
                      <X class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                      :aria-label="showPassword ? t('auth.login.hidePassword') : t('auth.login.showPassword')"
                      :aria-pressed="showPassword"
                      :title="showPassword ? t('auth.login.hidePassword') : t('auth.login.showPassword')"
                      @click="showPassword = !showPassword"
                    >
                      <EyeOff v-if="showPassword" class="h-4 w-4" />
                      <Eye v-else class="h-4 w-4" />
                    </button>
                  </div>
                </div>
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

    <p v-if="version" class="absolute bottom-4 text-xs text-muted-foreground/70 tabular-nums">
      {{ appName }} v{{ version }}
    </p>
  </div>
</template>
