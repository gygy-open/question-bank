<script setup lang="ts">
import { ArrowUp, Loader2, Image as ImageIcon, X, Book, Plus } from '@lucide/vue'
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

const { t } = useI18n()
const chat = useGlobalChat()

const modelGroups = computed(() => {
  const models = chat.allModels.value
  const mine = models.filter(m => m.isPersonal)
  const shared = models.filter(m => !m.isPersonal)
  return mine.length && shared.length
    ? [{ label: t('chat.composer.myModels'), items: mine }, { label: t('chat.composer.globalModels'), items: shared }]
    : [{ label: '', items: models }]
})
const canSend = computed(() =>
  !chat.loading.value
  && !!chat.selectedModelId.value
  && (!!chat.input.value.trim() || chat.selectedImages.value.length > 0),
)

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
  <div class="shrink-0 px-3 pb-3 pt-1">
    <form
      class="rounded-lg border bg-muted/30 transition-colors focus-within:border-ring dark:bg-input/30"
      @submit.prevent="chat.sendMessage()"
    >
      <input ref="fileInputRef" type="file" multiple accept="image/*" class="hidden" @change="handleFileSelect" />

      <div v-if="chat.selectedImages.value.length > 0" class="flex gap-2 overflow-x-auto px-2 pt-2.5">
        <div v-for="(img, index) in chat.selectedImages.value" :key="index" class="relative shrink-0">
          <img
            :src="img"
            class="h-14 w-14 cursor-pointer rounded-md border object-cover transition-opacity hover:opacity-90"
            @click="chat.openPreview(img)"
          />
          <button
            type="button"
            class="absolute -right-1.5 -top-1.5 rounded-full bg-destructive p-0.5 text-destructive-foreground hover:bg-destructive/90"
            @click="chat.removeImage(index)"
          >
            <X class="h-3 w-3" />
          </button>
        </div>
      </div>

      <Textarea
        v-model="chat.input.value"
        data-chat-input
        :placeholder="chat.isVisionCapable.value ? t('chat.composer.placeholderVision') : t('chat.composer.placeholder')"
        class="max-h-[200px] min-h-[44px] resize-none rounded-none border-0 bg-transparent px-3 py-2.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
        rows="1"
        @keydown.enter="onEnter"
        @paste="handlePaste"
      />

      <div class="flex items-center gap-0.5 px-1.5 pb-1.5">
        <Button
          v-if="chat.isVisionCapable.value"
          type="button"
          variant="ghost"
          size="icon"
          class="h-7 w-7 shrink-0 text-muted-foreground"
          :title="t('chat.composer.uploadImage')"
          @click="triggerFileInput"
        >
          <Plus class="h-4 w-4" />
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          class="h-7 shrink-0 gap-1.5 px-2 text-xs font-normal text-muted-foreground"
          :title="t('prompts.manager.title')"
          @click="chat.isPromptManagerOpen.value = true"
        >
          <Book class="h-3.5 w-3.5" />
          {{ t('prompts.manager.title') }}
        </Button>

        <Select v-model="chat.selectedModelId.value">
          <SelectTrigger
            size="sm"
            class="h-7 min-w-0 max-w-[55%] gap-1 border-0 bg-transparent px-2 text-xs text-muted-foreground shadow-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-0 dark:bg-transparent dark:hover:bg-accent"
          >
            <SelectValue :placeholder="t('chat.composer.selectModel')" />
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
              {{ t('chat.composer.noModels') }}
            </div>
          </SelectContent>
        </Select>

        <Button
          type="submit"
          size="icon"
          class="ml-auto h-7 w-7 shrink-0"
          :title="t('chat.composer.send')"
          :disabled="!canSend"
        >
          <Loader2 v-if="chat.loading.value" class="h-4 w-4 animate-spin" />
          <ArrowUp v-else class="h-4 w-4" />
        </Button>
      </div>
    </form>
  </div>
</template>
