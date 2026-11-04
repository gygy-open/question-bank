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
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar
} from '@/components/ui/sidebar'
import type { SidebarProps } from "@/components/ui/sidebar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import UserProfileDialog from '~/components/UserProfileDialog.vue'
import ChangePasswordDialog from '~/components/ChangePasswordDialog.vue'
import { useColorMode, useIntervalFn } from '@vueuse/core'
import { BookOpen, ChevronsUpDown, ListChecks, Shapes, Images, Inbox, ListTree, LogOut, Settings, User, Users, Tags, Library, KeyRound, Activity, Info, Moon, Sun, Lock, Languages, Check, LayoutDashboard, PanelLeftClose, PanelLeftOpen } from '@lucide/vue'

const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: "icon",
})

const route = useRoute()
const { state: sidebarState, toggleSidebar } = useSidebar()
const { t, locale, locales, setLocale } = useI18n()
const { user, logout } = useAuth()
const { isAdmin, isManagerSomewhere } = usePermissions()
const router = useRouter()
const isProfileOpen = ref(false)
const isChangePasswordOpen = ref(false)
const colorMode = useColorMode()
const toggleColorMode = () => {
  colorMode.value = colorMode.value === 'dark' ? 'light' : 'dark'
}

// 待审核的导入数;识别在后台完成,用户不在导入页时也要看得到。
const { reviewCount: importReviewCount, refreshSummary: refreshImportSummary } = useImportQueue()
useIntervalFn(() => { if (user.value) refreshImportSummary() }, 30_000)
watch(user, (current) => { if (current) refreshImportSummary() }, { immediate: true })

// 题干结构化总开关:关闭时隐藏「拆解审核」「元素类型」入口。
const { enabled: structureEnabled, refresh: refreshStructureEnabled } = useStructureEnabled()
watch(user, (current) => { if (current) refreshStructureEnabled() }, { immediate: true })

const sidebarToggleLabel = computed(() =>
  sidebarState.value === 'expanded' ? t('common.collapseSidebar') : t('common.expandSidebar'),
)

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
        <SidebarMenuItem>
          <SubjectSelector />
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupContent class="flex flex-col gap-3">
          <div>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/'" :class="navActiveClass">
                  <NuxtLink to="/">
                    <LayoutDashboard />
                    <span>{{ t('nav.dashboard') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  as-child
                  :is-active="route.path === '/questions' || route.path.startsWith('/questions/') || route.path === '/materials' || route.path.startsWith('/materials/')"
                  :class="navActiveClass"
                >
                  <NuxtLink to="/questions">
                    <BookOpen />
                    <span>{{ t('nav.questionBank') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  as-child
                  :is-active="route.path === '/imports' || route.path.startsWith('/imports/')"
                  :class="navActiveClass"
                >
                  <NuxtLink to="/imports">
                    <Inbox />
                    <span>{{ t('nav.import') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
                <SidebarMenuBadge v-if="importReviewCount" :title="t('nav.importReviewBadge', { count: importReviewCount })">
                  {{ importReviewCount }}
                </SidebarMenuBadge>
              </SidebarMenuItem>
              <SidebarMenuItem v-if="structureEnabled">
                <SidebarMenuButton as-child :is-active="route.path === '/structure/review'" :class="navActiveClass">
                  <NuxtLink to="/structure/review">
                    <ListChecks />
                    <span>{{ t('nav.structureReview') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>

          <div>
            <SidebarGroupLabel>{{ t('nav.compositionWorkbench') }}</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  as-child
                  :is-active="route.path === '/compositions/shared' || route.path.startsWith('/compositions/shared/')"
                  :class="navActiveClass"
                >
                  <NuxtLink to="/compositions/shared">
                    <Users />
                    <span>{{ t('nav.sharedSpace') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  as-child
                  :is-active="route.path === '/compositions/personal' || route.path.startsWith('/compositions/personal/')"
                  :class="navActiveClass"
                >
                  <NuxtLink to="/compositions/personal">
                    <Lock />
                    <span>{{ t('nav.personalSpace') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>

          <div>
            <SidebarGroupLabel>{{ t('nav.subjectResources') }}</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/knowledge-points'" :class="navActiveClass">
                  <NuxtLink to="/knowledge-points">
                    <ListTree />
                    <span>{{ t('nav.knowledgePoints') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/tags'" :class="navActiveClass">
                  <NuxtLink to="/tags">
                    <Tags />
                    <span>{{ t('nav.tags') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem v-if="structureEnabled">
                <SidebarMenuButton as-child :is-active="route.path === '/structure/types'" :class="navActiveClass">
                  <NuxtLink to="/structure/types">
                    <Shapes />
                    <span>{{ t('nav.structureTypes') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/media'" :class="navActiveClass">
                  <NuxtLink to="/media">
                    <Images />
                    <span>{{ t('nav.media') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>

      <!-- 系统：LAN 共享与超管入口归为同一簇 -->
      <div>
        <SidebarGroupLabel>{{ t('nav.system') }}</SidebarGroupLabel>
        <SidebarMenu>
          <LanShareDialog />
          <template v-if="user?.is_superuser">
            <SidebarMenuItem>
              <SidebarMenuButton as-child :is-active="route.path === '/users'" :class="navActiveClass">
                <NuxtLink to="/users">
                  <Users />
                  <span>{{ t('nav.users') }}</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem v-if="user?.id === 1">
              <SidebarMenuButton as-child :is-active="route.path === '/activity-logs'" :class="navActiveClass">
                <NuxtLink to="/activity-logs">
                  <Activity />
                  <span>{{ t('nav.activityLogs') }}</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </template>
          <SidebarMenuItem v-if="isAdmin || isManagerSomewhere">
            <SidebarMenuButton as-child :is-active="route.path === '/subjects'" :class="navActiveClass">
              <NuxtLink to="/subjects">
                <Library />
                <span>{{ t('nav.subjects') }}</span>
              </NuxtLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton as-child :is-active="route.path === '/settings'" :class="navActiveClass">
              <NuxtLink to="/settings">
                <Settings />
                <span>{{ isAdmin ? t('nav.systemSettings') : t('nav.settings') }}</span>
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
                {{ t('userMenu.profile') }}
              </DropdownMenuItem>
              <DropdownMenuItem @click="isChangePasswordOpen = true">
                <KeyRound class="mr-2 size-4" />
                {{ t('userMenu.changePassword') }}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="toggleColorMode">
                <component :is="colorMode === 'dark' ? Sun : Moon" class="mr-2 size-4" />
                {{ colorMode === 'dark' ? t('userMenu.lightMode') : t('userMenu.darkMode') }}
              </DropdownMenuItem>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Languages class="mr-2 size-4" />
                  {{ t('language.label') }}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuItem v-for="l in locales" :key="l.code" @click="setLocale(l.code)">
                    <Check class="mr-2 size-4" :class="l.code === locale ? 'opacity-100' : 'opacity-0'" />
                    {{ l.name }}
                  </DropdownMenuItem>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuItem @click="router.push('/about')">
                <Info class="mr-2 size-4" />
                {{ t('userMenu.about') }}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="handleLogout">
                <LogOut class="mr-2 size-4" />
                {{ t('userMenu.logout') }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton
            class="text-sidebar-foreground/70"
            :tooltip="sidebarToggleLabel"
            :aria-label="sidebarToggleLabel"
            @click="toggleSidebar"
          >
            <component :is="sidebarState === 'expanded' ? PanelLeftClose : PanelLeftOpen" />
            <span>{{ sidebarToggleLabel }}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>
    <SidebarRail />
    <UserProfileDialog v-model:open="isProfileOpen" />
    <ChangePasswordDialog v-model:open="isChangePasswordOpen" />
  </Sidebar>
</template>