<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from 'tiptap-markdown'
import Placeholder from '@tiptap/extension-placeholder'
import Image from '@tiptap/extension-image'
import { Bold, Italic, List, ListOrdered, Sigma, Quote, ImageIcon, FileCode, Square } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import MathEditor from './MathEditor.vue'
import { MathExtension } from '../extensions/MathExtension'

const props = defineProps<{
  modelValue: string | null
  placeholder?: string
  minHeight?: string
}>()

const emit = defineEmits(['update:modelValue'])

const isSourceMode = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const adjustTextareaHeight = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    textarea.style.height = `${textarea.scrollHeight}px`
  }
}

const handleInput = (e: Event) => {
  const target = e.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
  adjustTextareaHeight()
}

const toggleSourceMode = () => {
  isSourceMode.value = !isSourceMode.value
  // When switching back to visual mode, update the editor content
  if (!isSourceMode.value && editor.value && props.modelValue !== null) {
    editor.value.commands.setContent(props.modelValue)
  } else if (isSourceMode.value) {
    nextTick(adjustTextareaHeight)
  }
}

// Image upload function
const uploadImage = async (file: File): Promise<string> => {
  const formData = new FormData()
  formData.append('file', file)
  
  try {
    const response = await fetch('/api/v1/upload/image', {
      method: 'POST',
      body: formData,
    })
    
    if (!response.ok) {
      throw new Error('Upload failed')
    }
    
    const data = await response.json()
    return data.url
  } catch (error) {
    console.error('Image upload failed:', error)
    throw error
  }
}

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit,
    MathExtension.configure({
      onEdit: ({ latex, update }) => {
        currentLatex.value = latex
        currentMathUpdate.value = update
        isMathDialogOpen.value = true
      }
    }),
    Placeholder.configure({
      placeholder: props.placeholder || '请输入内容...',
    }),
    Image.configure({
      inline: true,
      allowBase64: true,
    }),
    Markdown.configure({
      html: true,
      transformPastedText: true,
      transformCopiedText: true,
    }),
  ],
  editorProps: {
    attributes: {
      class: cn(
        'prose prose-sm sm:prose-base dark:prose-invert focus:outline-none max-w-none p-4',
        props.minHeight || 'min-h-[150px]'
      ),
    },
    handlePaste(view, event) {
      const items = event.clipboardData?.items
      
      // Handle Image Paste
      if (items) {
        for (let i = 0; i < items.length; i++) {
          if (items[i].type.indexOf('image') !== -1) {
            event.preventDefault()
            const file = items[i].getAsFile()
            if (file) {
              uploadImage(file).then(url => {
                editor.value?.chain().focus().setImage({ src: url }).run()
              }).catch(err => {
                console.error('Failed to upload pasted image:', err)
              })
            }
            return true
          }
        }
      }

      return false
    },
    handleDrop(view, event, slice, moved) {
      if (!moved && event.dataTransfer?.files?.length) {
        const images = Array.from(event.dataTransfer.files).filter(file => 
          file.type.startsWith('image/')
        )
        
        if (images.length > 0) {
          event.preventDefault()
          
          const { schema } = view.state
          const coordinates = view.posAtCoords({ left: event.clientX, top: event.clientY })
          
          images.forEach(file => {
            uploadImage(file).then(url => {
              const node = schema.nodes.image.create({ src: url })
              const transaction = view.state.tr.insert(coordinates?.pos || 0, node)
              view.dispatch(transaction)
            }).catch(err => {
              console.error('Failed to upload dropped image:', err)
            })
          })
          
          return true
        }
      }
      return false
    },
  },
  onUpdate: ({ editor }) => {
    const markdown = editor.storage.markdown.getMarkdown()
    console.log('Editor content updated:', markdown)
    emit('update:modelValue', markdown)
  },
})

watch(() => props.modelValue, (newValue) => {
  if (isSourceMode.value) {
    nextTick(adjustTextareaHeight)
    return
  }

  if (editor.value && newValue !== editor.value.storage.markdown.getMarkdown()) {
    editor.value.commands.setContent(newValue)
  }
})

onBeforeUnmount(() => {
  editor.value?.destroy()
})

// Math Dialog Logic
const isMathDialogOpen = ref(false)
const currentLatex = ref('')
const currentMathUpdate = ref<((attrs: any) => void) | null>(null)

// Image upload logic
const fileInputRef = ref<HTMLInputElement | null>(null)

const triggerImageUpload = () => {
  fileInputRef.value?.click()
}

const handleImageUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  
  try {
    const url = await uploadImage(file)
    editor.value?.chain().focus().setImage({ src: url }).run()
  } catch (error) {
    console.error('Failed to upload image:', error)
  }
  
  // Reset input
  if (target) target.value = ''
}

const onInteractOutside = (event: any) => {
  const target = event.target as HTMLElement
  // Prevent closing if clicking on mathlive virtual keyboard
  if (
    target?.closest('.ML__keyboard') || 
    target?.closest('.MLK__keyboard') || 
    target?.closest('.ML__virtual-keyboard') ||
    target?.closest('.action-menu')
  ) {
    event.preventDefault()
  }
}

const openMathDialog = () => {
  currentLatex.value = ''
  currentMathUpdate.value = null
  isMathDialogOpen.value = true
}

const insertBoxedText = () => {
  currentLatex.value = '\\boxed{\\text{内容}}'
  currentMathUpdate.value = null
  isMathDialogOpen.value = true
}

const insertMath = () => {
  if (!currentLatex.value) return
  
  if (currentMathUpdate.value) {
    // Update existing math node
    currentMathUpdate.value({ latex: currentLatex.value })
  } else {
    // Insert new math node
    // Use the command to insert the custom node instead of text
    editor.value?.chain().focus().insertContent({
      type: 'math',
      attrs: { latex: currentLatex.value }
    }).run()
  }
  
  isMathDialogOpen.value = false
  currentMathUpdate.value = null
}
</script>

<template>
  <div class="border rounded-md bg-background">
    <!-- Toolbar -->
    <div v-if="editor" class="flex items-center gap-1 p-2 border-b bg-muted/40 flex-wrap">
      <Button variant="ghost" size="icon" @click="editor.chain().focus().toggleBold().run()" :class="{ 'bg-muted': editor.isActive('bold') }" :disabled="isSourceMode">
        <Bold class="w-4 h-4" />
      </Button>
      <Button variant="ghost" size="icon" @click="editor.chain().focus().toggleItalic().run()" :class="{ 'bg-muted': editor.isActive('italic') }" :disabled="isSourceMode">
        <Italic class="w-4 h-4" />
      </Button>
      <div class="w-px h-4 bg-border mx-1"></div>
      <Button variant="ghost" size="icon" @click="editor.chain().focus().toggleBulletList().run()" :class="{ 'bg-muted': editor.isActive('bulletList') }" :disabled="isSourceMode">
        <List class="w-4 h-4" />
      </Button>
      <Button variant="ghost" size="icon" @click="editor.chain().focus().toggleOrderedList().run()" :class="{ 'bg-muted': editor.isActive('orderedList') }" :disabled="isSourceMode">
        <ListOrdered class="w-4 h-4" />
      </Button>
      <div class="w-px h-4 bg-border mx-1"></div>
      <Button variant="ghost" size="icon" @click="editor.chain().focus().toggleBlockquote().run()" :class="{ 'bg-muted': editor.isActive('blockquote') }" :disabled="isSourceMode">
        <Quote class="w-4 h-4" />
      </Button>
      
      <div class="w-px h-4 bg-border mx-1"></div>
      
      <!-- Math Button -->
      <Button variant="ghost" size="icon" @click="openMathDialog" title="插入数学公式" :disabled="isSourceMode">
        <Sigma class="w-4 h-4" />
      </Button>
      
      <!-- Boxed Text Button -->
      <Button variant="ghost" size="icon" @click="insertBoxedText" title="带框文字" :disabled="isSourceMode">
        <Square class="w-4 h-4" />
      </Button>

      <!-- Image Button -->
      <Button variant="ghost" size="icon" @click="triggerImageUpload" title="插入图片" :disabled="isSourceMode">
        <ImageIcon class="w-4 h-4" />
      </Button>

      <div class="w-px h-4 bg-border mx-1"></div>

      <!-- Source Mode Button -->
      <Button variant="ghost" size="icon" @click="toggleSourceMode" :class="{ 'bg-muted': isSourceMode }" title="源代码">
        <FileCode class="w-4 h-4" />
      </Button>
    </div>
    
    <!-- Hidden file input -->
    <input 
      ref="fileInputRef" 
      type="file" 
      accept="image/*" 
      class="hidden" 
      @change="handleImageUpload"
    />
    
    <!-- Editor Content -->
    <EditorContent v-show="!isSourceMode" :editor="editor" />
    <textarea
      ref="textareaRef"
      v-show="isSourceMode"
      :value="modelValue"
      @input="handleInput"
      class="w-full p-4 font-mono text-sm bg-background resize-none focus:outline-none border-0 overflow-hidden"
      :class="[minHeight || 'min-h-[150px]']"
    ></textarea>

    <!-- Math Dialog -->
    <Dialog v-model:open="isMathDialogOpen">
      <DialogContent class="sm:max-w-[600px]" @interact-outside="onInteractOutside" :trap-focus="false">
        <DialogHeader>
          <DialogTitle>编辑数学公式</DialogTitle>
          <DialogDescription>使用 LaTeX 语法创建或编辑数学节点</DialogDescription>
        </DialogHeader>
        
        <div class="py-4">
          <MathEditor v-model="currentLatex" @confirm="insertMath" />
        </div>
        
        <DialogFooter>
          <Button variant="outline" @click="isMathDialogOpen = false">取消</Button>
          <Button @click="insertMath">插入</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
