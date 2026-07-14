<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'

const props = defineProps<{
  content: string
}>()

const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true
})

md.use(texmath, {
  engine: katex,
  delimiters: 'dollars',
  katexOptions: { 
    macros: { 
      "\\RR": "\\mathbb{R}",
      "\\CC": "\\mathbb{C}",
      "\\ZZ": "\\mathbb{Z}"
    },
    strict: false,
    throwOnError: false,
    errorColor: '#cc0000',
    trust: true
  }
})

const renderedContent = computed(() => {
  if (!props.content) return ''
  
  let content = props.content

  // 1. Fix Pandoc's multiline attributes and convert width/height to style
  // Pandoc outputs {width="1in" height="1in"}, but browsers ignore width="1in" on img tags.
  // We convert it to style="width:1in;height:1in"
  content = content.replace(/\{([^{}]*?)\}/g, (match, inner) => {
    if (inner.match(/(?:width|height)\s*=/)) {
      // Flatten newlines
      let attrs = inner.replace(/[\r\n]+/g, ' ')
      
      const styles: string[] = []
      
      // Extract width="value"
      attrs = attrs.replace(/\bwidth="([^"]*)"/g, (m, val) => {
        styles.push(`width:${val}`)
        return ''
      })
      
      // Extract height="value"
      attrs = attrs.replace(/\bheight="([^"]*)"/g, (m, val) => {
        styles.push(`height:${val}`)
        return ''
      })
      
      if (styles.length > 0) {
        attrs = attrs.trim() + ` style="${styles.join(';')}"`
      }
      
      return '{' + attrs + '}'
    }
    return match
  })

  // 2. Fix detached attributes: ![](...) \n {style=...} -> ![](...) {style=...}
  content = content.replace(/(\!\[.*?\]\(.*?\))\s+(\{.*?\})/g, '$1$2')

  // 3. Convert image with attributes to HTML img tag to avoid using markdown-it-attrs
  // Matches: ![alt](src){attrs}
  content = content.replace(/!\[(.*?)\]\((.*?)\)\{([^{}]*?)\}/g, (match, alt, src, attrs) => {
    // src might contain title: url "title"
    let url = src
    let title = ''
    const titleMatch = src.match(/^(\S+)\s+"(.*)"$/)
    if (titleMatch) {
      url = titleMatch[1]
      title = titleMatch[2]
    }
    
    let imgTag = `<img src="${url}" alt="${alt}"`
    if (title) {
      imgTag += ` title="${title}"`
    }
    
    // Parse attributes: .class #id key="value" key=value
    let attrString = attrs.trim()
    
    // Extract classes
    const classes: string[] = []
    attrString = attrString.replace(/\.([a-zA-Z0-9_-]+)/g, (m, c) => {
      classes.push(c)
      return ''
    })
    
    // Extract id
    let id = ''
    attrString = attrString.replace(/#([a-zA-Z0-9_-]+)/g, (m, i) => {
      id = i
      return ''
    })
    
    if (classes.length > 0) {
      imgTag += ` class="${classes.join(' ')}"`
    }
    if (id) {
      imgTag += ` id="${id}"`
    }
    
    // Remaining should be key="value" pairs
    imgTag += ` ${attrString}`
    imgTag += `>`
    return imgTag
  })

  // 4. Normalize LaTeX delimiters
  // Fix loose dollar delimiters: $ ... $ -> $...$
  // Use a regex that matches single $ delimiters (not $$) and trims the content
  // This fixes cases like "$ a $" which markdown-it-texmath ignores (it requires "$a$")
  content = content.replace(/(?<!\$|\\)\$(?!\$)(.*?)(?<!\\|\$)\$(?!\$)/g, (match, inner) => {
    return '$' + inner.trim() + '$'
  })

  return md.render(content)
})
</script>

<template>
  <div class="prose prose-sm dark:prose-invert max-w-none break-words" v-html="renderedContent"></div>
</template>

<style scoped>
/* Add any specific markdown styles if needed, though tailwind typography (prose) handles most */
</style>