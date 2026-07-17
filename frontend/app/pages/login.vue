<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { Loader2 } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

definePageMeta({
  layout: 'empty'
})

const { login } = useAuth()
const router = useRouter()
const { $api } = useNuxtApp()

const isLoading = ref(false)

// 若系统尚未完成首次初始化，引导至安装向导
onMounted(async () => {
  try {
    const res = await $api<{ configured: boolean }>('/setup/status')
    if (!res.configured) {
      router.replace('/setup')
    }
  } catch {
    // 忽略状态探测失败
  }
})

const formSchema = toTypedSchema(z.object({
  username: z.string().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
}))

const form = useForm({
  validationSchema: formSchema,
})

const onSubmit = form.handleSubmit(async (values) => {
  isLoading.value = true
  try {
    await login({ username: values.username, password: values.password })
    toast.success('登录成功')
    router.push('/')
  } catch (error: any) {
    toast.error(error.message || '登录失败')
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
        <CardTitle class="text-2xl text-center">登录账户</CardTitle>
        <CardDescription class="text-center">
          输入您的用户名和密码进行登录
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit="onSubmit">
          <div class="grid gap-4">
            <FormField v-slot="{ componentField }" name="username">
              <FormItem>
                <FormLabel>用户名</FormLabel>
                <FormControl>
                  <Input type="text" placeholder="admin" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
            
            <FormField v-slot="{ componentField }" name="password">
              <FormItem>
                <FormLabel>密码</FormLabel>
                <FormControl>
                  <Input type="password" placeholder="******" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
            
            <Button type="submit" :disabled="isLoading" class="w-full">
              <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
              登录
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
