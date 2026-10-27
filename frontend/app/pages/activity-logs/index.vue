<script setup lang="ts">
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Pagination,
  PaginationEllipsis,
  PaginationFirst,
  PaginationLast,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { X } from '@lucide/vue'
import { format } from 'date-fns'
import PageHeader from '~/components/PageHeader.vue'

const { t, te } = useI18n()
const { user } = useAuth()
const router = useRouter()

if (user.value?.id !== 1) {
  router.push('/')
}

const page = ref(1)
const pageSize = ref(20)
const selectedUserId = ref<string>('all')

const queryParams = computed(() => {
  const params: any = {
    page: page.value,
    size: pageSize.value
  }
  if (selectedUserId.value && selectedUserId.value !== 'all') {
    params.user_id = selectedUserId.value
  }
  return params
})

const { data: usersData } = await useAPI<any[]>('/users', {
  query: { limit: 100 } // Fetch first 100 users for filter
})

const { data, pending, refresh } = await useAPI<any>('/activity-logs', {
  query: queryParams
})

const logs = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total || 0)

const resetFilter = () => {
  selectedUserId.value = 'all'
  page.value = 1
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return format(new Date(dateStr), 'yyyy-MM-dd HH:mm:ss')
}

const formatDetails = (details: any) => {
  if (!details) return '-'
  return JSON.stringify(details)
}

const logLabel = (group: 'actions' | 'resourceTypes', value?: string | null) => {
  if (!value) return '-'
  const key = `activityLogs.${group}.${value.replace(/_(\w)/g, (_, c: string) => c.toUpperCase())}`
  return te(key) ? t(key) : value
}
</script>

<template>
  <PageHeader :title="t('nav.activityLogs')">
    <template #actions>
      <div class="flex items-center gap-2">
        <Select v-model="selectedUserId">
          <SelectTrigger class="w-[180px]">
            <SelectValue :placeholder="t('activityLogs.selectUser')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{{ t('activityLogs.allUsers') }}</SelectItem>
            <SelectItem v-for="u in usersData" :key="u.id" :value="String(u.id)">
              {{ u.full_name || u.username }}
            </SelectItem>
          </SelectContent>
        </Select>
        <Button v-if="selectedUserId !== 'all'" variant="ghost" size="icon" @click="resetFilter">
          <X class="w-4 h-4" />
        </Button>
      </div>
      <div class="text-sm text-muted-foreground">
        {{ t('activityLogs.total', { count: total }) }}
      </div>
    </template>
  </PageHeader>

  <div class="p-6">
    <div class="rounded-md border bg-card mb-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead class="w-[80px]">ID</TableHead>
            <TableHead>{{ t('activityLogs.columns.user') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.action') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.resourceType') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.resourceId') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.ipAddress') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.time') }}</TableHead>
            <TableHead>{{ t('activityLogs.columns.details') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="pending">
            <TableCell colspan="8" class="text-center py-10">
              {{ t('common.loading') }}
            </TableCell>
          </TableRow>
          <TableRow v-else-if="!logs || logs.length === 0">
            <TableCell colspan="8" class="text-center py-10">
              {{ t('activityLogs.empty') }}
            </TableCell>
          </TableRow>
          <TableRow v-else v-for="log in logs" :key="log.id">
            <TableCell>{{ log.id }}</TableCell>
            <TableCell>
              <div v-if="log.user">
                <div class="font-medium">{{ log.user.full_name || log.user.username }}</div>
                <div class="text-xs text-muted-foreground">{{ log.user.username }}</div>
              </div>
              <span v-else class="text-muted-foreground">-</span>
            </TableCell>
            <TableCell>{{ logLabel('actions', log.action) }}</TableCell>
            <TableCell>{{ logLabel('resourceTypes', log.resource_type) }}</TableCell>
            <TableCell>{{ log.resource_id || '-' }}</TableCell>
            <TableCell>{{ log.ip_address || '-' }}</TableCell>
            <TableCell>{{ formatDate(log.created_at) }}</TableCell>
            <TableCell class="max-w-[300px] truncate" :title="formatDetails(log.details)">
              {{ formatDetails(log.details) }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Pagination -->
    <div v-if="total > 0" class="flex justify-center pb-8">
      <Pagination v-model:page="page" :total="total" :sibling-count="1" show-edges :default-page="1"
        :items-per-page="pageSize">
        <PaginationContent v-slot="{ items }" class="flex items-center gap-1">
          <PaginationFirst />
          <PaginationPrevious />
          <template v-for="(item, index) in items">
            <PaginationItem v-if="item.type === 'page'" :key="index" :value="item.value" as-child>
              <Button class="w-10 h-10 p-0" :variant="item.value === page ? 'default' : 'outline'">
                {{ item.value }}
              </Button>
            </PaginationItem>
            <PaginationEllipsis v-else :key="item.type" :index="index" />
          </template>
          <PaginationNext />
          <PaginationLast />
        </PaginationContent>
      </Pagination>
    </div>
  </div>
</template>
