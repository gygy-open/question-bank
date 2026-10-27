<script setup lang="ts">
import { getApiErrorCodeMessage } from '@/lib/apiErrors'
import { Loader2, Database, HardDrive, Server, Check } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { SetupStatus } from '@/types'

definePageMeta({
  layout: 'empty',
})

const { t } = useI18n()
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
    toast.success(t('setup.toast.dbConnected'))
  } catch (e: any) {
    toast.error(getApiErrorCodeMessage(e) || e?.data?.detail || t('setup.toast.connectFailed'))
  } finally {
    testing.value = false
  }
}

async function configureDatabase() {
  if (dbType.value === 'mysql' && !testPassed.value) {
    toast.error(t('setup.toast.testMysqlFirst'))
    return
  }
  submitting.value = true
  try {
    await $api('/setup/database', { method: 'POST', body: dbPayload() })
    toast.success(t('setup.toast.dbReady'))
    step.value = 2
  } catch (e: any) {
    toast.error(getApiErrorCodeMessage(e) || e?.data?.detail || t('setup.toast.dbInitFailed'))
  } finally {
    submitting.value = false
  }
}

async function createAdmin() {
  if (admin.username.trim().length < 1) {
    toast.error(t('setup.toast.usernameRequired'))
    return
  }
  if (admin.password.length < 6) {
    toast.error(t('setup.toast.passwordMin', { min: 6 }))
    return
  }
  if (admin.password !== admin.confirm) {
    toast.error(t('setup.toast.passwordMismatch'))
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
    toast.success(t('setup.toast.done'))
    router.replace('/login')
  } catch (e: any) {
    toast.error(getApiErrorCodeMessage(e) || e?.data?.detail || t('setup.toast.initFailed'))
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
        <CardTitle class="text-2xl text-center">{{ t('setup.title') }}</CardTitle>
        <CardDescription class="text-center">
          {{ dbPreconfigured ? t('setup.descriptionDbReady') : t('setup.description') }}
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
            <span class="text-sm" :class="step >= 1 ? 'font-medium' : 'text-muted-foreground'">{{ t('setup.steps.database') }}</span>
          </div>
          <Separator class="w-8 shrink-0 data-[orientation=horizontal]:w-8" />
          <div class="flex items-center gap-2">
            <span
              class="flex h-7 w-7 items-center justify-center rounded-full text-sm"
              :class="step >= 2 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
            >2</span>
            <span class="text-sm" :class="step >= 2 ? 'font-medium' : 'text-muted-foreground'">{{ t('setup.steps.admin') }}</span>
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
              <span class="text-xs text-muted-foreground">{{ t('setup.sqliteHint') }}</span>
            </button>
            <button
              type="button"
              class="flex flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors"
              :class="dbType === 'mysql' ? 'border-primary ring-1 ring-primary' : 'hover:bg-muted/50'"
              @click="dbType = 'mysql'"
            >
              <Server class="h-5 w-5" />
              <span class="font-medium">MySQL</span>
              <span class="text-xs text-muted-foreground">{{ t('setup.mysqlHint') }}</span>
            </button>
          </div>

          <!-- MySQL 连接信息 -->
          <div v-if="dbType === 'mysql'" class="grid gap-3 rounded-lg border p-4">
            <div class="grid grid-cols-3 gap-3">
              <div class="col-span-2 grid gap-1.5">
                <Label>{{ t('setup.mysql.host') }}</Label>
                <Input v-model="mysql.host" placeholder="localhost" />
              </div>
              <div class="grid gap-1.5">
                <Label>{{ t('setup.mysql.port') }}</Label>
                <Input v-model.number="mysql.port" type="number" placeholder="3306" />
              </div>
            </div>
            <div class="grid gap-1.5">
              <Label>{{ t('setup.mysql.database') }}</Label>
              <Input v-model="mysql.database" placeholder="question_bank" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="grid gap-1.5">
                <Label>{{ t('setup.mysql.user') }}</Label>
                <Input v-model="mysql.user" placeholder="question_bank" />
              </div>
              <div class="grid gap-1.5">
                <Label>{{ t('setup.mysql.password') }}</Label>
                <Input v-model="mysql.password" type="password" placeholder="******" />
              </div>
            </div>
            <Button type="button" variant="outline" :disabled="testing" @click="testConnection">
              <Loader2 v-if="testing" class="mr-2 h-4 w-4 animate-spin" />
              <Check v-else-if="testPassed" class="mr-2 h-4 w-4 text-green-600" />
              <Database v-else class="mr-2 h-4 w-4" />
              {{ t('setup.mysql.test') }}
            </Button>
          </div>

          <Button type="button" class="w-full" :disabled="submitting" @click="configureDatabase">
            <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
            {{ dbType === 'sqlite' ? t('setup.startNow') : t('setup.next') }}
          </Button>
        </div>

        <!-- 步骤 2：管理员账号 -->
        <div v-else class="grid gap-4">
          <div class="grid gap-1.5">
            <Label>{{ t('setup.admin.username') }}</Label>
            <Input v-model="admin.username" placeholder="admin" />
          </div>
          <div class="grid gap-1.5">
            <Label>{{ t('setup.admin.password') }}</Label>
            <Input v-model="admin.password" type="password" :placeholder="t('setup.admin.passwordPlaceholder', { min: 6 })" />
          </div>
          <div class="grid gap-1.5">
            <Label>{{ t('setup.admin.confirm') }}</Label>
            <Input v-model="admin.confirm" type="password" :placeholder="t('setup.admin.confirmPlaceholder')" />
          </div>
          <Button type="button" class="w-full" :disabled="submitting" @click="createAdmin">
            <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
            {{ t('setup.finish') }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
