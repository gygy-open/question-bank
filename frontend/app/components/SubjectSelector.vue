<script setup lang="ts">
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarMenuButton, useSidebar } from '@/components/ui/sidebar'
import { ChevronsUpDown, AlertTriangle, Info, Check, Library } from '@lucide/vue'
import { toast } from 'vue-sonner'

const { t } = useI18n()

const { currentSubject, subjects, hasSubjects, setSubject } = useSubjectContext()
const { isAdmin } = usePermissions()
const router = useRouter()
const { state } = useSidebar()

const selectSubject = async (id: number) => {
  try {
    await setSubject(id)
  } catch {
    toast.error(t('subjectSelector.switchFailed'))
  }
}

const goCreateSubject = () => router.push('/subjects?create=true')
</script>

<template>
  <DropdownMenu v-if="hasSubjects">
    <DropdownMenuTrigger as-child>
      <SidebarMenuButton
        size="lg"
        :aria-label="t('subjectSelector.switch')"
        class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
      >
        <SubjectAvatar v-if="currentSubject" :id="currentSubject.id" :name="currentSubject.name" />
        <div v-else class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Library class="size-4" />
        </div>
        <span class="min-w-0 flex-1 truncate font-semibold">
          {{ currentSubject?.name || t('subjectSelector.select') }}
        </span>
        <ChevronsUpDown class="ml-auto size-4 shrink-0 text-muted-foreground" />
      </SidebarMenuButton>
    </DropdownMenuTrigger>
    <DropdownMenuContent
      class="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
      :side="state === 'collapsed' ? 'right' : 'bottom'"
      align="start"
      :side-offset="4"
    >
      <DropdownMenuItem v-for="s in subjects" :key="s.id" @click="selectSubject(s.id)">
        <SubjectAvatar :id="s.id" :name="s.name" size="sm" class="mr-2" />
        <span class="min-w-0 flex-1 truncate">{{ s.name }}</span>
        <Check v-if="s.id === currentSubject?.id" class="ml-2 size-4 shrink-0 text-muted-foreground" />
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <!-- 管理员且系统尚无学科:引导创建第一个学科 -->
  <SidebarMenuButton
    v-else-if="isAdmin"
    size="lg"
    :aria-label="t('subjectSelector.createFirst')"
    class="text-destructive hover:bg-destructive/10 hover:text-destructive"
    @click="goCreateSubject"
  >
    <div class="flex aspect-square size-8 items-center justify-center rounded-lg border border-destructive/50 bg-destructive/10">
      <AlertTriangle class="size-4" />
    </div>
    <div class="flex flex-col gap-0.5 leading-none">
      <span class="truncate font-semibold">{{ t('subjectSelector.createFirst') }}</span>
    </div>
  </SidebarMenuButton>

  <!-- 普通用户未被分配学科:提示联系管理员(无创建权限) -->
  <SidebarMenuButton
    v-else
    size="lg"
    :aria-label="t('subjectSelector.noneAvailable')"
    class="text-muted-foreground"
  >
    <div class="flex aspect-square size-8 items-center justify-center rounded-lg border bg-muted">
      <Info class="size-4" />
    </div>
    <div class="flex min-w-0 flex-col gap-0.5 leading-none">
      <span class="truncate font-semibold">{{ t('subjectSelector.noneAvailable') }}</span>
      <span class="truncate text-xs text-muted-foreground">{{ t('subjectSelector.contactAdmin') }}</span>
    </div>
  </SidebarMenuButton>
</template>
