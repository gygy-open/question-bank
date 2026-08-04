<script setup lang="ts">
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Library, AlertTriangle } from '@lucide/vue'
import { toast } from 'vue-sonner'

const { currentSubjectId, currentSubject, subjects, hasSubjects, setSubject } = useSubjectContext()
const router = useRouter()

// Bridge number <-> string for the Select (shadcn Select works with strings).
const selectedValue = computed({
  get: () => (currentSubjectId.value != null ? String(currentSubjectId.value) : undefined),
  set: async (val: string | undefined) => {
    if (!val) return
    try {
      await setSubject(Number(val))
    } catch {
      toast.error('切换学科失败')
    }
  },
})

const goCreateSubject = () => router.push('/subjects?create=true')
</script>

<template>
  <Select v-if="hasSubjects" v-model="selectedValue">
    <SelectTrigger
      class="w-full bg-primary/5 border-primary/20"
      aria-label="选择当前工作学科"
    >
      <div class="flex items-center gap-2 truncate">
        <Library class="size-4 shrink-0 text-primary" />
        <SelectValue placeholder="选择学科">
          {{ currentSubject?.name }}
        </SelectValue>
      </div>
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="s in subjects" :key="s.id" :value="String(s.id)">
        {{ s.name }}
      </SelectItem>
    </SelectContent>
  </Select>

  <button
    v-else
    type="button"
    class="flex w-full items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive hover:bg-destructive/15"
    @click="goCreateSubject"
  >
    <AlertTriangle class="size-4 shrink-0" />
    <span class="truncate">请先创建学科</span>
  </button>
</template>
