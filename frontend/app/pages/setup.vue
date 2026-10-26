<script setup lang="ts">
import { Loader2, Database, HardDrive, Server, Check } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { SetupStatus } from '@/types'

definePageMeta({
  layout: 'empty',
})

const { $api } = useNuxtApp()
const router = useRouter()

type DbType = 'sqlite' | 'mysql'

const step = ref<1 | 2>(1)
const dbType = ref<DbType>('sqlite')

const mysql = reactive({
  host: 'localhost',
  port: 3306,
  user: '',
  password: '',
  database: 'question_bank',
})

const admin = reactive({
  username: 'admin',
  password: '',
  confirm: '',
})

const testing = ref(false)
const testPassed = ref(false)
const submitting = ref(false)
// 首次探测完成前不渲染步骤，避免 Docker 场景下第 1 步一闪而过
const ready = ref(false)
// 数据库在进入本页前已就绪（Docker / 环境变量 DB_URL，或上次只完成了第 1 步）
const dbPreconfigured = ref(false)

onMounted(async () => {
  try {
    const res = await $api<SetupStatus>('/setup/status')
    if (res.db_configured && res.admin_initialized) {
      router.replace('/login')
      return
    }
    if (res.db_configured) {
      dbPreconfigured.value = true
      step.value = 2
    }
  } catch {
    // 忽略，保持在安装页
  } finally {
    ready.value = true
  }
})

function dbPayload() {
  return dbType.value === 'sqlite'
    ? { db_type: 'sqlite' as const }
    : { db_type: 'mysql' as const, mysql: { ...mysql } }
}

// 切换数据库类型时重置连接测试状态
watch(dbType, () => {
  testPassed.value = false
})

async function testConnection() {
  testing.value = true
  testPassed.value = false
  try {
    await $api('/setup/test-db', { method: 'POST', body: dbPayload() })
    testPassed.value = true
    toast.success('数据库连接成功')
  } catch (e: any) {
    toast.error(e?.data?.detail || '连接失败')
  } finally {
    testing.value = false
  }
}

async function configureDatabase() {
  if (dbType.value === 'mysql' && !testPassed.value) {
    toast.error('请先测试 MySQL 连接')
    return
  }
  submitting.value = true
  try {
    await $api('/setup/database', { method: 'POST', body: dbPayload() })
    toast.success('数据库已就绪')
    step.value = 2
  } catch (e: any) {
    toast.error(e?.data?.detail || '数据库初始化失败')
  } finally {
    submitting.value = false
  }
}

async function createAdmin() {
  if (admin.username.trim().length < 1) {
    toast.error('请输入管理员用户名')
    return
  }
  if (admin.password.length < 6) {
    toast.error('密码至少 6 位')
    return
  }
  if (admin.password !== admin.confirm) {
    toast.error('两次输入的密码不一致')
    return
  }
  submitting.value = true
  try {
    await $api('/setup/admin', {
      method: 'POST',
      body: {
        username: admin.username.trim(),
        password: admin.password,
      },
    })
    toast.success('初始化完成，请登录')
    router.replace('/login')
  } catch (e: any) {
    toast.error(e?.data?.detail || '初始化失败')
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
          <img src="/logo.svg" alt="Logo" class="h-14 w-auto" />
        </div>
        <CardTitle class="text-2xl text-center">系统初始化</CardTitle>
        <CardDescription class="text-center">
          {{ dbPreconfigured ? '数据库已就绪，请创建首个管理员账号' : '首次使用，请完成数据库与管理员账号配置' }}
        </CardDescription>

        <!-- 步骤指示 -->
        <div class="flex items-center justify-center gap-2 pt-4">
          <div class="flex items-center gap-2">
            <span
              class="flex h-7 w-7 items-center justify-center rounded-full text-sm"
              :class="step >= 1 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
            >
              <Check v-if="step > 1" class="h-4 w-4" />
              <template v-else>1</template>
            </span>
            <span class="text-sm" :class="step >= 1 ? 'font-medium' : 'text-muted-foreground'">数据库</span>
          </div>
          <Separator class="w-8 shrink-0 data-[orientation=horizontal]:w-8" />
          <div class="flex items-center gap-2">
            <span
              class="flex h-7 w-7 items-center justify-center rounded-full text-sm"
              :class="step >= 2 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
            >2</span>
            <span class="text-sm" :class="step >= 2 ? 'font-medium' : 'text-muted-foreground'">管理员</span>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div v-if="!ready" class="flex justify-center py-8">
          <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
        </div>

        <!-- 步骤 1：数据库 -->
        <div v-else-if="step === 1" class="grid gap-4">
          <div class="grid grid-cols-2 gap-3">
            <button
              type="button"
              class="flex flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors"
              :class="dbType === 'sqlite' ? 'border-primary ring-1 ring-primary' : 'hover:bg-muted/50'"
              @click="dbType = 'sqlite'"
            >
              <HardDrive class="h-5 w-5" />
              <span class="font-medium">SQLite</span>
              <span class="text-xs text-muted-foreground">单机 / 零配置，推荐个人使用</span>
            </button>
            <button
              type="button"
              class="flex flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors"
              :class="dbType === 'mysql' ? 'border-primary ring-1 ring-primary' : 'hover:bg-muted/50'"
              @click="dbType = 'mysql'"
            >
              <Server class="h-5 w-5" />
              <span class="font-medium">MySQL</span>
              <span class="text-xs text-muted-foreground">内网团队共享，多人协作</span>
            </button>
          </div>

          <!-- MySQL 连接信息 -->
          <div v-if="dbType === 'mysql'" class="grid gap-3 rounded-lg border p-4">
            <div class="grid grid-cols-3 gap-3">
              <div class="col-span-2 grid gap-1.5">
                <Label>主机</Label>
                <Input v-model="mysql.host" placeholder="localhost" />
              </div>
              <div class="grid gap-1.5">
                <Label>端口</Label>
                <Input v-model.number="mysql.port" type="number" placeholder="3306" />
              </div>
            </div>
            <div class="grid gap-1.5">
              <Label>数据库名</Label>
              <Input v-model="mysql.database" placeholder="question_bank" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="grid gap-1.5">
                <Label>用户名</Label>
                <Input v-model="mysql.user" placeholder="question_bank" />
              </div>
              <div class="grid gap-1.5">
                <Label>密码</Label>
                <Input v-model="mysql.password" type="password" placeholder="******" />
              </div>
            </div>
            <Button type="button" variant="outline" :disabled="testing" @click="testConnection">
              <Loader2 v-if="testing" class="mr-2 h-4 w-4 animate-spin" />
              <Check v-else-if="testPassed" class="mr-2 h-4 w-4 text-green-600" />
              <Database v-else class="mr-2 h-4 w-4" />
              测试连接
            </Button>
          </div>

          <Button type="button" class="w-full" :disabled="submitting" @click="configureDatabase">
            <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
            {{ dbType === 'sqlite' ? '直接开始' : '下一步' }}
          </Button>
        </div>

        <!-- 步骤 2：管理员账号 -->
        <div v-else class="grid gap-4">
          <div class="grid gap-1.5">
            <Label>管理员用户名</Label>
            <Input v-model="admin.username" placeholder="admin" />
          </div>
          <div class="grid gap-1.5">
            <Label>密码</Label>
            <Input v-model="admin.password" type="password" placeholder="至少 6 位" />
          </div>
          <div class="grid gap-1.5">
            <Label>确认密码</Label>
            <Input v-model="admin.confirm" type="password" placeholder="再次输入密码" />
          </div>
          <Button type="button" class="w-full" :disabled="submitting" @click="createAdmin">
            <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
            完成初始化
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
