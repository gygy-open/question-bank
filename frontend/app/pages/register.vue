<script setup lang="ts">
import { getApiErrorCodeMessage } from '@/lib/apiErrors'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'

definePageMeta({
  layout: 'empty'
})

const { t } = useI18n()
const router = useRouter()
const { $api } = useNuxtApp()

const isLoading = ref(false)
const checking = ref(true)
const requiresApproval = ref(false)

onMounted(async () => {
  try {
    const res = await $api<{ enabled: boolean; requires_approval: boolean }>('/register/config')
    if (!res.enabled) {
      toast.error(t('auth.register.disabled'))
      router.replace('/login')
      return
    }
    requiresApproval.value = res.requires_approval
  } catch {
    router.replace('/login')
    return
  } finally {
    checking.value = false
  }
})

// schema 放在 computed 里，切换语言后校验文案随之更新（页面会被 keepalive 缓存）。
const formSchema = computed(() => toTypedSchema(z.object({
  username: z.string({ required_error: t('auth.register.usernameRequired') }).min(1, t('auth.register.usernameRequired')),
  full_name: z.string({ required_error: t('auth.register.fullNameRequired') }).min(1, t('auth.register.fullNameRequired')),
  password: z.string({ required_error: t('auth.register.passwordMin', { min: 6 }) }).min(6, t('auth.register.passwordMin', { min: 6 })),
  confirm_password: z.string({ required_error: t('auth.register.confirmRequired') }).min(1, t('auth.register.confirmRequired')),
}).refine((v) => v.password === v.confirm_password, {
  message: t('auth.register.passwordMismatch'),
  path: ['confirm_password'],
})))

const form = useForm({
  validationSchema: formSchema,
})

const onSubmit = form.handleSubmit(async (values) => {
  isLoading.value = true
  try {
    const res = await $api<{ ok: boolean; requires_approval: boolean }>('/register', {
      method: 'POST',
      body: {
        username: values.username,
        full_name: values.full_name,
        password: values.password,
      },
    })
    if (res.requires_approval) {
      toast.success(t('auth.register.successPendingApproval'))
    } else {
      toast.success(t('auth.register.success'))
    }
    router.push('/login')
  } catch (error: any) {
    toast.error(getApiErrorCodeMessage(error) || error.data?.detail || error.message || t('auth.register.failed'))
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <div class="flex h-screen w-full items-center justify-center bg-muted/40 px-4">
    <Card class="w-full sm:w-[400px]">
      <CardHeader class="space-y-1">
        <div class="flex justify-center mb-4">
          <img src="/logo.svg" alt="Logo" class="h-16 w-auto" />
        </div>
        <CardTitle class="text-2xl text-center">{{ t('auth.register.title') }}</CardTitle>
        <CardDescription class="text-center">
          {{ t('auth.register.description') }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="checking" class="flex justify-center py-8">
          <Loader2 class="h-6 w-6 animate-spin" />
        </div>
        <form v-else @submit="onSubmit">
          <div class="grid gap-4">
            <FormField v-slot="{ componentField }" name="username">
              <FormItem>
                <FormLabel>{{ t('auth.login.username') }}</FormLabel>
                <FormControl>
                  <Input type="text" :placeholder="t('auth.register.usernameRequired')" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ componentField }" name="full_name">
              <FormItem>
                <FormLabel>{{ t('auth.register.fullName') }}</FormLabel>
                <FormControl>
                  <Input type="text" :placeholder="t('auth.register.fullNameRequired')" v-bind="componentField" />
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

            <FormField v-slot="{ componentField }" name="confirm_password">
              <FormItem>
                <FormLabel>{{ t('auth.register.confirmPassword') }}</FormLabel>
                <FormControl>
                  <Input type="password" placeholder="******" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <p v-if="requiresApproval" class="text-xs text-muted-foreground">
              {{ t('auth.register.approvalHint') }}
            </p>

            <Button type="submit" :disabled="isLoading" class="w-full">
              <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
              {{ t('auth.register.submit') }}
            </Button>

            <div class="text-center text-sm text-muted-foreground">
              {{ t('auth.register.hasAccount') }}
              <NuxtLink to="/login" class="text-primary hover:underline">{{ t('auth.register.backToLogin') }}</NuxtLink>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
