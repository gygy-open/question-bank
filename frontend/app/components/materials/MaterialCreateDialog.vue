<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getApiErrorDetail } from '@/lib/questionGroupEditor'
import type { RichDoc, Stimulus } from '@/types'

const props = defineProps<{ open: boolean, subjectId: number | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean], created: [material: Stimulus] }>()
const { createMaterial } = useMaterials()
const content = ref<RichDoc>(null)
const source = ref('')
const saving = ref(false)
const errorMessage = ref('')

watch(() => props.open, open => {
  if (open) { content.value = null; source.value = ''; errorMessage.value = '' }
})

const submit = async () => {
  if (!props.subjectId || isEmptyRichDoc(content.value)) { errorMessage.value = '请填写题目材料内容'; return }
  saving.value = true
  try {
    const material = await createMaterial(props.subjectId, {
      content: content.value, status: 'draft', visibility: 'public', source: source.value.trim() || null,
    })
    emit('created', material)
    emit('update:open', false)
    toast.success('题目材料已创建并选中')
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '创建题目材料失败')
  } finally { saving.value = false }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-3xl">
      <DialogHeader><DialogTitle>快速创建题目材料</DialogTitle><DialogDescription>新题目材料将保存为公开草稿，并自动用于当前题组。</DialogDescription></DialogHeader>
      <div class="space-y-4"><div class="space-y-2"><Label>题目材料内容</Label><RichEditor v-model="content" /></div><div class="space-y-2"><Label for="quick-material-source">来源</Label><Input id="quick-material-source" v-model="source" placeholder="可选" /></div><p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p></div>
      <DialogFooter><Button variant="outline" @click="emit('update:open', false)">取消</Button><Button :disabled="saving" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" />创建并选中</Button></DialogFooter>
    </DialogContent>
  </Dialog>
</template>