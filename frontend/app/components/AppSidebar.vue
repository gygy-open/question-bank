<script setup lang="ts">
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail
} from '@/components/ui/sidebar'
import type { SidebarProps } from "@/components/ui/sidebar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import CustomSidebarTrigger from '~/components/CustomSidebarTrigger.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import UserProfileDialog from '~/components/UserProfileDialog.vue'
import ChangePasswordDialog from '~/components/ChangePasswordDialog.vue'
import { BookOpen, ChevronsUpDown, CirclePlus, ListTree, LogOut, Settings, Sparkles, User, Users, Tags, Library, HelpCircle, MessageSquare, KeyRound, Activity, ListTodo, Download, RefreshCw, FileText } from '@lucide/vue'
import { toast } from 'vue-sonner'

const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: "icon",
})

const route = useRoute()
const { user, logout } = useAuth()
const router = useRouter()
const isProfileOpen = ref(false)
const isChangePasswordOpen = ref(false)

const { state: updateState, check: checkUpdate } = useUpdateCheck()

const handleCheckUpdate = async () => {
  await checkUpdate(true)
  if (updateState.value.error) {
    toast.error('检查更新失败', { description: updateState.value.error })
  } else if (updateState.value.hasUpdate) {
    window.open(updateState.value.releaseUrl, '_blank')
  } else {
    toast.success('已是最新版本', { description: `当前版本 v${updateState.value.current}` })
  }
}

const handleLogout = () => {
  logout()
  router.push('/login')
}
</script>

<template>
  <Sidebar v-bind="props">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem
          class="flex flex-row items-center gap-1 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:gap-2"
        >
          <div class="min-w-0 flex-1 group-data-[collapsible=icon]:w-full">
            <SubjectSelector />
          </div>
          <CustomSidebarTrigger
            class="ml-2 h-8 w-8 shrink-0 rounded-md hover:bg-sidebar-accent group-data-[collapsible=icon]:ml-0"
          />
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupContent class="flex flex-col gap-2">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton :is-active="route.query.create === 'true'" as-child tooltip="新增题目"
                class="border border-primary text-primary hover:bg-primary hover:text-primary-foreground active:bg-primary/90 active:text-primary-foreground min-w-8 duration-200 ease-linear">
                <NuxtLink to="/questions?create=true">
                  <CirclePlus />
                  <span>新增题目</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/questions'">
                <NuxtLink to="/questions">
                  <BookOpen />
                  <span>题目管理</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path.startsWith('/papers')">
                <NuxtLink to="/papers">
                  <FileText />
                  <span>我的试卷</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/import/smart'">
                <NuxtLink to="/import/smart">
                  <Sparkles />
                  <span>智能导入</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/imports'">
                <NuxtLink to="/imports">
                  <ListTodo />
                  <span>批量智能导入</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/chat'">
                <NuxtLink to="/chat">
                  <MessageSquare />
                  <span>AI 助手</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/knowledge-points'">
                <NuxtLink to="/knowledge-points">
                  <ListTree />
                  <span>知识点管理</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/tags'">
                <NuxtLink to="/tags">
                  <Tags />
                  <span>标签管理</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/subjects'">
                <NuxtLink to="/subjects">
                  <Library />
                  <span>科目管理</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem v-if="user?.is_superuser">
          <SidebarMenuButton
            :class="updateState.hasUpdate ? 'text-primary' : ''"
            :tooltip="updateState.hasUpdate ? `发现新版本 v${updateState.latest}，点击下载安装程序` : '检查更新'"
            @click="handleCheckUpdate"
          >
            <Download v-if="updateState.hasUpdate" />
            <RefreshCw v-else :class="updateState.checking ? 'animate-spin' : ''" />
            <span>{{ updateState.hasUpdate ? `有新版 v${updateState.latest}` : '检查更新' }}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton as-child :is-active="route.path === '/manual'">
            <NuxtLink to="/manual">
              <HelpCircle />
              <span>使用手册</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem v-if="user?.is_superuser">
          <SidebarMenuButton as-child :is-active="route.path === '/users'">
            <NuxtLink to="/users">
              <Users />
              <span>用户管理</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem v-if="user?.id === 1">
          <SidebarMenuButton as-child :is-active="route.path === '/activity-logs'">
            <NuxtLink to="/activity-logs">
              <Activity />
              <span>行为日志</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem v-if="user?.is_superuser">
          <SidebarMenuButton as-child :is-active="route.path === '/settings'">
            <NuxtLink to="/settings">
              <Settings />
              <span>系统设置</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <LanShareDialog />
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg"
                class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground">
                <Avatar class="h-8 w-8 rounded-lg">
                  <AvatarImage :src="user?.avatar_url || ''" :alt="user?.username" />
                  <AvatarFallback class="rounded-lg">{{ user?.username?.slice(0, 2).toUpperCase() }}</AvatarFallback>
                </Avatar>
                <div class="grid flex-1 text-left text-sm leading-tight">
                  <span class="truncate font-semibold">{{ user?.full_name || user?.username }}</span>
                  <span class="truncate text-xs">{{ user?.username }}</span>
                </div>
                <ChevronsUpDown class="ml-auto size-4" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg" side="bottom"
              align="end" :side-offset="4">
              <DropdownMenuItem @click="isProfileOpen = true">
                <User class="mr-2 size-4" />
                个人资料
              </DropdownMenuItem>
              <DropdownMenuItem @click="isChangePasswordOpen = true">
                <KeyRound class="mr-2 size-4" />
                修改密码
              </DropdownMenuItem>
              <DropdownMenuItem @click="handleLogout">
                <LogOut class="mr-2 size-4" />
                退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>
    <SidebarRail />
    <UserProfileDialog v-model:open="isProfileOpen" />
    <ChangePasswordDialog v-model:open="isChangePasswordOpen" />
  </Sidebar>
</template>