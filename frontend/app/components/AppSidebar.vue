<script setup lang="ts">
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator
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
import AboutDialog from '~/components/AboutDialog.vue'
import { useColorMode } from '@vueuse/core'
import { BookOpen, ChevronsUpDown, CirclePlus, ListTree, LogOut, Settings, Sparkles, User, Users, Tags, Library, HelpCircle, MessageSquare, KeyRound, Activity, Layers, ClipboardList, Info, Moon, Sun } from '@lucide/vue'

const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: "icon",
})

const route = useRoute()
const { user, logout } = useAuth()
const router = useRouter()
const isProfileOpen = ref(false)
const isChangePasswordOpen = ref(false)
const isAboutOpen = ref(false)
const colorMode = useColorMode()
const toggleColorMode = () => {
  colorMode.value = colorMode.value === 'dark' ? 'light' : 'dark'
}

const handleLogout = () => {
  logout()
  router.push('/login')
}

// 左侧彩色条 + 主题色高亮当前导航项，不修改 ui/sidebar 原始组件
const navActiveClass = 'border-l-2 border-transparent data-[active=true]:border-l-primary data-[active=true]:bg-primary/10 data-[active=true]:text-primary data-[active=true]:font-medium group-data-[collapsible=icon]:border-l-0'
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
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <SidebarGroup>
        <SidebarGroupContent class="flex flex-col gap-3">
          <div>
            <SidebarGroupLabel>内容</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/questions'" :class="navActiveClass">
                  <NuxtLink to="/questions">
                    <BookOpen />
                    <span>题目管理</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path.startsWith('/papers')" :class="navActiveClass">
                  <NuxtLink to="/papers">
                    <ClipboardList />
                    <span>我的试卷</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/chat'" :class="navActiveClass">
                  <NuxtLink to="/chat">
                    <MessageSquare />
                    <span>AI 助手</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>

          <div>
            <SidebarGroupLabel>导入</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/import/smart'" :class="navActiveClass">
                  <NuxtLink to="/import/smart">
                    <Sparkles />
                    <span>智能导入</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/imports'" :class="navActiveClass">
                  <NuxtLink to="/imports">
                    <Layers />
                    <span>批量智能导入</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>

          <div>
            <SidebarGroupLabel>知识库</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/knowledge-points'" :class="navActiveClass">
                  <NuxtLink to="/knowledge-points">
                    <ListTree />
                    <span>知识点管理</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/tags'" :class="navActiveClass">
                  <NuxtLink to="/tags">
                    <Tags />
                    <span>标签管理</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/subjects'" :class="navActiveClass">
                  <NuxtLink to="/subjects">
                    <Library />
                    <span>科目管理</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton :tooltip="colorMode === 'dark' ? '切换到浅色模式' : '切换到深色模式'" @click="toggleColorMode">
            <component :is="colorMode === 'dark' ? Sun : Moon" />
            <span>{{ colorMode === 'dark' ? '浅色模式' : '深色模式' }}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton as-child :is-active="route.path === '/manual'" :class="navActiveClass">
            <NuxtLink to="/manual">
              <HelpCircle />
              <span>使用手册</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton tooltip="版本信息与检查更新" @click="isAboutOpen = true">
            <Info />
            <span>关于</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <!-- 与"关于"归为一组：都是系统状态信息，而非高频操作 -->
        <LanShareDialog />
      </SidebarMenu>

      <div v-if="user?.is_superuser">
        <SidebarGroupLabel>系统管理</SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton as-child :is-active="route.path === '/users'" :class="navActiveClass">
              <NuxtLink to="/users">
                <Users />
                <span>用户管理</span>
              </NuxtLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem v-if="user?.id === 1">
            <SidebarMenuButton as-child :is-active="route.path === '/activity-logs'" :class="navActiveClass">
              <NuxtLink to="/activity-logs">
                <Activity />
                <span>行为日志</span>
              </NuxtLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton as-child :is-active="route.path === '/settings'" :class="navActiveClass">
              <NuxtLink to="/settings">
                <Settings />
                <span>系统设置</span>
              </NuxtLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </div>

      <SidebarSeparator class="mx-0" />

      <SidebarMenu>
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
                <ChevronsUpDown class="text-sidebar-foreground/50 ml-auto size-4" />
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
    <AboutDialog v-model:open="isAboutOpen" :is-superuser="user?.is_superuser" />
  </Sidebar>
</template>