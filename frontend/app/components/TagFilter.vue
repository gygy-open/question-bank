<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Tag, TagCategory } from '~/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Check, ChevronsUpDown, Tag as TagIcon, X } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'

const props = defineProps<{
  tags: Tag[]
  categories: TagCategory[]
  modelValue: string[] // Array of selected tag IDs
}>()

const emit = defineEmits(['update:modelValue'])

const open = ref(false)

// Group tags by category
const tagsByCategory = computed(() => {
  const grouped: Record<string, Tag[]> = {}
  
  // Initialize with all categories
  props.categories.forEach(cat => {
    grouped[cat.slug] = []
  })
  // Also add 'general' if not present
  if (!grouped['general']) grouped['general'] = []

  props.tags.forEach(tag => {
    const cat = tag.category || 'general'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(tag)
  })

  return grouped
})

const selectedTags = computed(() => {
  return props.tags.filter(tag => props.modelValue.includes(String(tag.id)))
})

const toggleTag = (tagId: string) => {
  const current = [...props.modelValue]
  const index = current.indexOf(tagId)
  if (index >= 0) {
    current.splice(index, 1)
  } else {
    current.push(tagId)
  }
  emit('update:modelValue', current)
}

const clearTags = () => {
  emit('update:modelValue', [])
}

const getCategoryName = (slug: string) => {
  return props.categories.find(c => c.slug === slug)?.name || slug
}
</script>

<template>
  <div class="flex items-center space-x-2">
    <Popover v-model:open="open">
      <PopoverTrigger as-child>
        <Button
          variant="outline"
          role="combobox"
          :aria-expanded="open"
          class="h-10 w-full justify-between"
        >
          <div class="flex items-center truncate">
            <TagIcon class="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <span v-if="selectedTags.length === 0">选择标签...</span>
            <span v-else class="truncate">
                {{ selectedTags.length }} 个标签已选
            </span>
          </div>
          <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-[300px] p-0" align="start">
        <Command>
          <CommandInput placeholder="搜索标签..." />
          <CommandList class="max-h-[400px] overflow-y-auto">
            <CommandEmpty>未找到标签</CommandEmpty>
            
            <template v-for="category in categories" :key="category.id">
              <CommandGroup 
                v-if="tagsByCategory[category.slug]?.length" 
                :heading="category.name"
              >
                <CommandItem
                  v-for="tag in tagsByCategory[category.slug]"
                  :key="tag.id"
                  :value="tag.name"
                  @select="toggleTag(String(tag.id))"
                >
                  <div
                    :class="cn(
                      'mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary',
                      modelValue.includes(String(tag.id))
                        ? 'bg-primary text-primary-foreground'
                        : 'opacity-50 [&_svg]:invisible'
                    )"
                  >
                    <Check class="h-4 w-4" />
                  </div>
                  <div class="flex items-center gap-2">
                    <span>{{ tag.name }}</span>
                    <div 
                        class="w-2 h-2 rounded-full" 
                        :style="{ backgroundColor: tag.color }"
                        v-if="tag.color"
                    />
                  </div>
                </CommandItem>
              </CommandGroup>
              <CommandSeparator v-if="tagsByCategory[category.slug]?.length" />
            </template>

            <!-- Handle tags with unknown categories or 'general' if not in categories list -->
             <CommandGroup 
                v-if="tagsByCategory['general']?.length && !categories.find(c => c.slug === 'general')" 
                heading="通用"
              >
                <CommandItem
                  v-for="tag in tagsByCategory['general']"
                  :key="tag.id"
                  :value="tag.name"
                  @select="toggleTag(String(tag.id))"
                >
                  <div
                    :class="cn(
                      'mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary',
                      modelValue.includes(String(tag.id))
                        ? 'bg-primary text-primary-foreground'
                        : 'opacity-50 [&_svg]:invisible'
                    )"
                  >
                    <Check class="h-4 w-4" />
                  </div>
                  <span>{{ tag.name }}</span>
                </CommandItem>
              </CommandGroup>

          </CommandList>
          <div class="flex items-center justify-between p-2 border-t">
             <span class="text-xs text-muted-foreground">
                已选 {{ selectedTags.length }} 个
             </span>
             <Button 
                variant="ghost" 
                size="sm" 
                class="h-auto px-2 py-1 text-xs"
                @click="clearTags"
                v-if="selectedTags.length > 0"
            >
                清除
             </Button>
          </div>
        </Command>
      </PopoverContent>
    </Popover>
  </div>
</template>
