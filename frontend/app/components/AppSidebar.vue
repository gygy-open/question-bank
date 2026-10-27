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
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import CustomSidebarTrigger from '~/components/CustomSidebarTrigger.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import UserProfileDialog from '~/components/UserProfileDialog.vue'
import ChangePasswordDialog from '~/components/ChangePasswordDialog.vue'
import { useColorMode } from '@vueuse/core'
import { BookOpen, ChevronsUpDown, Images, ListTree, LogOut, Settings, Sparkles, User, Users, Tags, Library, KeyRound, Activity, Layers, Info, Moon, Sun, Lock, Languages, Check, LayoutDashboard } from '@lucide/vue'

const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: "icon",
})

const route = useRoute()
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
            <SidebarGroupLabel>{{ t('nav.import') }}</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/import/smart'" :class="navActiveClass">
                  <NuxtLink to="/import/smart">
                    <Sparkles />
                    <span>{{ t('nav.smartImport') }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton as-child :is-active="route.path === '/imports'" :class="navActiveClass">
                  <NuxtLink to="/imports">
                    <Layers />
                    <span>{{ t('nav.batchImport') }}</span>
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
      </SidebarMenu>
    </SidebarFooter>
    <SidebarRail />
    <UserProfileDialog v-model:open="isProfileOpen" />
    <ChangePasswordDialog v-model:open="isChangePasswordOpen" />
  </Sidebar>
</template>