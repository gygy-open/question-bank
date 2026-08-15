<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'

definePageMeta({
  layout: 'empty'
})

const router = useRouter()
const { $api } = useNuxtApp()

const isLoading = ref(false)
const checking = ref(true)
const requiresApproval = ref(false)

onMounted(async () => {
  try {
    const res = await $api<{ enabled: boolean; requires_approval: boolean }>('/register/config')
    if (!res.enabled) {
      toast.error('注册功能未开放')
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

const formSchema = toTypedSchema(z.object({
  username: z.string().min(1, '请输入用户名'),
  full_name: z.string().min(1, '请输入姓名'),
  password: z.string().min(6, '密码长度不能少于 6 位'),
  confirm_password: z.string().min(1, '请再次输入密码'),
}).refine((v) => v.password === v.confirm_password, {
  message: '两次输入的密码不一致',
  path: ['confirm_password'],
}))

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
      toast.success('注册成功，请等待管理员审核后登录')
    } else {
      toast.success('注册成功，请登录')
    }
    router.push('/login')
  } catch (error: any) {
    toast.error(error.data?.detail || error.message || '注册失败')
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
        <CardTitle class="text-2xl text-center">注册账户</CardTitle>
        <CardDescription class="text-center">
          创建一个新账户以使用系统
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
                <FormLabel>用户名</FormLabel>
                <FormControl>
                  <Input type="text" placeholder="请输入用户名" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ componentField }" name="full_name">
              <FormItem>
                <FormLabel>姓名</FormLabel>
                <FormControl>
                  <Input type="text" placeholder="请输入姓名" v-bind="componentField" />
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

            <FormField v-slot="{ componentField }" name="confirm_password">
              <FormItem>
                <FormLabel>确认密码</FormLabel>
                <FormControl>
                  <Input type="password" placeholder="******" v-bind="componentField" />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <p v-if="requiresApproval" class="text-xs text-muted-foreground">
              注册后需要管理员审核通过才能登录。
            </p>

            <Button type="submit" :disabled="isLoading" class="w-full">
              <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
              注册
            </Button>

            <div class="text-center text-sm text-muted-foreground">
              已有账户？
              <NuxtLink to="/login" class="text-primary hover:underline">返回登录</NuxtLink>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
