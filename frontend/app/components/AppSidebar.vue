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
} from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import UserProfileDialog from '~/components/UserProfileDialog.vue'
import ChangePasswordDialog from '~/components/ChangePasswordDialog.vue'
import { BookOpen, ChevronsUpDown, CirclePlus, ListTree, LogOut, Settings, Sparkles, User, Users, Tags, Library, HelpCircle, MessageSquare, KeyRound, Activity, ListTodo } from 'lucide-vue-next'

const route = useRoute()
const { user, logout } = useAuth()
const router = useRouter()
const isProfileOpen = ref(false)
const isChangePasswordOpen = ref(false)
const config = useRuntimeConfig()

const handleLogout = () => {
  logout()
  router.push('/login')
}
</script>

<template>
  <Sidebar collapsible="offcanvas">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" as-child>
            <a href="#">
              <div
                class="flex aspect-square size-8 items-center justify-center rounded-lg text-primary-foreground">
                <img src="/logo.svg" alt="题库系统" class="size-8" />
              </div>
              <div class="flex flex-col gap-0.5 leading-none">
                <span class="font-semibold">{{ config.public.appName }}</span>
              </div>
            </a>
          </SidebarMenuButton>
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
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg"
                class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground">
                <Avatar class="h-8 w-8 rounded-lg">
                  <AvatarImage :src="user?.avatar_url" :alt="user?.username" />
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
    <UserProfileDialog v-model:open="isProfileOpen" />
    <ChangePasswordDialog v-model:open="isChangePasswordOpen" />
  </Sidebar>
</template>