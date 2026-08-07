<script setup lang="ts">
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarMenuButton, useSidebar } from '@/components/ui/sidebar'
import { ChevronsUpDown, AlertTriangle } from '@lucide/vue'
import { toast } from 'vue-sonner'

// Cycle a fixed palette by subject id so each subject keeps a stable color.
const SUBJECT_COLORS = [
  'bg-red-500', 'bg-orange-500', 'bg-amber-500', 'bg-lime-500',
  'bg-emerald-500', 'bg-teal-500', 'bg-cyan-500', 'bg-blue-500',
  'bg-indigo-500', 'bg-violet-500', 'bg-fuchsia-500', 'bg-pink-500',
]
const getSubjectColor = (id: number) => SUBJECT_COLORS[id % SUBJECT_COLORS.length]
const getSubjectInitial = (name: string) => name.trim().charAt(0) || '?'

const { currentSubject, subjects, hasSubjects, setSubject } = useSubjectContext()
const router = useRouter()
const config = useRuntimeConfig()
const { state } = useSidebar()

const selectSubject = async (id: number) => {
  try {
    await setSubject(id)
  } catch {
    toast.error('切换学科失败')
  }
}

const goCreateSubject = () => router.push('/subjects?create=true')
</script>

<template>
  <DropdownMenu v-if="hasSubjects">
    <DropdownMenuTrigger as-child>
      <SidebarMenuButton
        size="lg"
        aria-label="切换学科"
        class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
      >
        <div class="flex aspect-square size-8 items-center justify-center rounded-lg text-primary-foreground">
          <img src="/logo.svg" alt="题库系统" class="size-8" />
        </div>
        <div class="flex min-w-0 flex-col gap-0.5 leading-none">
          <span class="flex min-w-0 items-center gap-1">
            <span class="truncate font-semibold">{{ currentSubject?.name || '选择学科' }}</span>
            <ChevronsUpDown class="size-3.5 shrink-0 text-muted-foreground" />
          </span>
          <span class="truncate text-xs text-muted-foreground">{{ config.public.appName }}</span>
        </div>
      </SidebarMenuButton>
    </DropdownMenuTrigger>
    <DropdownMenuContent
      class="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
      :side="state === 'collapsed' ? 'right' : 'bottom'"
      align="start"
      :side-offset="4"
    >
      <DropdownMenuItem v-for="s in subjects" :key="s.id" @click="selectSubject(s.id)">
        <div
          class="mr-2 flex size-5 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold text-white"
          :class="getSubjectColor(s.id)"
        >
          {{ getSubjectInitial(s.name) }}
        </div>
        {{ s.name }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <SidebarMenuButton
    v-else
    size="lg"
    aria-label="请先创建学科"
    class="text-destructive hover:bg-destructive/10 hover:text-destructive"
    @click="goCreateSubject"
  >
    <div class="flex aspect-square size-8 items-center justify-center rounded-lg border border-destructive/50 bg-destructive/10">
      <AlertTriangle class="size-4" />
    </div>
    <div class="flex flex-col gap-0.5 leading-none">
      <span class="truncate font-semibold">请先创建学科</span>
    </div>
  </SidebarMenuButton>
</template>
