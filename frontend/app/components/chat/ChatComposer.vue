<script setup lang="ts">
import { Send, Loader2, Image as ImageIcon, X, Book } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useGlobalChat } from '@/composables/useGlobalChat'

const chat = useGlobalChat()

const modelGroups = computed(() => {
  const models = chat.allModels.value
  const mine = models.filter(m => m.isPersonal)
  const shared = models.filter(m => !m.isPersonal)
  return mine.length && shared.length
    ? [{ label: '我的模型', items: mine }, { label: '全局模型', items: shared }]
    : [{ label: '', items: models }]
})
const fileInputRef = ref<HTMLInputElement | null>(null)

const triggerFileInput = () => fileInputRef.value?.click()

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  chat.addFiles(Array.from(target.files))
  target.value = ''
}

const handlePaste = (event: ClipboardEvent) => {
  if (!chat.isVisionCapable.value) return
  const items = event.clipboardData?.items
  if (!items) return
  const files: File[] = []
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (files.length) chat.addFiles(files)
}

const onEnter = (e: KeyboardEvent) => {
  if (!e.shiftKey) {
    e.preventDefault()
    chat.sendMessage()
  }
}
</script>

<template>
  <div class="shrink-0 border-t p-3">
    <div v-if="chat.selectedImages.value.length > 0" class="mb-2 flex gap-2 overflow-x-auto py-1">
      <div v-for="(img, index) in chat.selectedImages.value" :key="index" class="relative shrink-0">
        <img
          :src="img"
          class="h-16 w-16 cursor-pointer rounded-md border object-cover transition-opacity hover:opacity-90"
          @click="chat.openPreview(img)"
        />
        <button
          type="button"
          class="absolute -right-2 -top-2 rounded-full bg-destructive p-0.5 text-destructive-foreground hover:bg-destructive/90"
          @click="chat.removeImage(index)"
        >
          <X class="h-3 w-3" />
        </button>
      </div>
    </div>

    <div class="mb-2">
      <Select v-model="chat.selectedModelId.value">
        <SelectTrigger class="h-8 w-full text-xs">
          <SelectValue placeholder="选择模型" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup v-for="group in modelGroups" :key="group.label">
            <SelectLabel v-if="group.label" class="text-xs">{{ group.label }}</SelectLabel>
            <SelectItem v-for="model in group.items" :key="model.id" :value="model.id.toString()">
              <div class="flex items-center gap-2">
                <span>{{ model.displayName }}</span>
                <ImageIcon v-if="model.is_vision_capable" class="h-3 w-3 text-muted-foreground" />
              </div>
            </SelectItem>
          </SelectGroup>
          <div v-if="!chat.allModels.value.length" class="px-2 py-1.5 text-xs text-muted-foreground">
            暂无可用模型，请在“设置 → 我的 AI 模型”中配置
          </div>
        </SelectContent>
      </Select>
    </div>

    <form class="flex items-end gap-1.5" @submit.prevent="chat.sendMessage()">
      <input ref="fileInputRef" type="file" multiple accept="image/*" class="hidden" @change="handleFileSelect" />

      <Button
        v-if="chat.isVisionCapable.value"
        type="button"
        variant="outline"
        size="icon"
        class="h-9 w-9 shrink-0"
        title="上传图片"
        @click="triggerFileInput"
      >
        <ImageIcon class="h-4 w-4" />
      </Button>

      <Button
        type="button"
        variant="outline"
        size="icon"
        class="h-9 w-9 shrink-0"
        title="常用指令"
        @click="chat.isPromptManagerOpen.value = true"
      >
        <Book class="h-4 w-4" />
      </Button>

      <Textarea
        v-model="chat.input.value"
        :placeholder="chat.isVisionCapable.value ? '输入消息... (支持粘贴图片)' : '输入消息...'"
        class="max-h-[160px] min-h-[38px] resize-none"
        rows="1"
        @keydown.enter="onEnter"
        @paste="handlePaste"
      />

      <Button
        type="submit"
        size="icon"
        class="h-9 w-9 shrink-0"
        :disabled="chat.loading.value || (!chat.input.value.trim() && chat.selectedImages.value.length === 0) || !chat.selectedModelId.value"
      >
        <Loader2 v-if="chat.loading.value" class="h-4 w-4 animate-spin" />
        <Send v-else class="h-4 w-4" />
      </Button>
    </form>
  </div>
</template>
