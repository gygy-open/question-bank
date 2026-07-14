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
import { Activity, X } from 'lucide-vue-next'
import { format } from 'date-fns'

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
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Activity class="w-6 h-6" />
        行为日志
      </h1>
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
          <Select v-model="selectedUserId">
            <SelectTrigger class="w-[180px]">
              <SelectValue placeholder="选择用户" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">所有用户</SelectItem>
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
          共 {{ total }} 条记录
        </div>
      </div>
    </div>

    <div class="rounded-md border bg-card mb-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead class="w-[80px]">ID</TableHead>
            <TableHead>用户</TableHead>
            <TableHead>行为</TableHead>
            <TableHead>资源类型</TableHead>
            <TableHead>资源ID</TableHead>
            <TableHead>IP地址</TableHead>
            <TableHead>时间</TableHead>
            <TableHead>详情</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="pending">
            <TableCell colspan="8" class="text-center py-10">
              加载中...
            </TableCell>
          </TableRow>
          <TableRow v-else-if="!logs || logs.length === 0">
            <TableCell colspan="8" class="text-center py-10">
              暂无日志
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
            <TableCell>{{ log.action }}</TableCell>
            <TableCell>{{ log.resource_type || '-' }}</TableCell>
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
