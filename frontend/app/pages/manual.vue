<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { BookOpen, Bold, Italic, List, ListOrdered, Quote, Code, Sigma, ImageIcon, Keyboard, Mouse } from 'lucide-vue-next'

definePageMeta({
  layout: 'default',
})
</script>

<template>
  <div class="flex flex-1 flex-col gap-4 p-4 pt-0">
    <!-- Header -->
    <header class="sticky top-0 z-10 flex h-14 items-center gap-4 border-b bg-background px-4 sm:static sm:h-auto sm:border-0 sm:bg-transparent sm:px-6 lg:h-[60px] lg:px-8">
      <div class="flex items-center gap-2">
        <BookOpen class="h-6 w-6" />
        <h1 class="text-xl font-semibold">系统使用手册</h1>
      </div>
    </header>

    <div class="mx-auto w-full max-w-5xl space-y-6 px-4 sm:px-6 lg:px-8">
      <!-- 编辑器使用说明 -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Code class="h-5 w-5" />
            编辑器使用说明
          </CardTitle>
          <CardDescription>
            本系统采用所见即所得的 Markdown 编辑器，支持丰富的文本格式和数学公式。
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-6">
          <!-- 基本格式 -->
          <div>
            <h3 class="text-lg font-semibold mb-3">基本文本格式</h3>
            <div class="space-y-3 text-sm">
              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Bold class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">粗体</p>
                  <p class="text-muted-foreground">点击工具栏的粗体按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+B</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown: <code class="px-1.5 py-0.5 bg-background rounded">**粗体文本**</code></p>
                </div>
              </div>

              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Italic class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">斜体</p>
                  <p class="text-muted-foreground">点击工具栏的斜体按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+I</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown: <code class="px-1.5 py-0.5 bg-background rounded">*斜体文本*</code></p>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <!-- 列表 -->
          <div>
            <h3 class="text-lg font-semibold mb-3">列表</h3>
            <div class="space-y-3 text-sm">
              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <List class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">无序列表</p>
                  <p class="text-muted-foreground">点击工具栏的列表按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+8</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown:</p>
                  <pre class="mt-1 px-2 py-1.5 bg-background rounded text-xs"><code>- 列表项 1
- 列表项 2
- 列表项 3</code></pre>
                </div>
              </div>

              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <ListOrdered class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">有序列表</p>
                  <p class="text-muted-foreground">点击工具栏的编号列表按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+7</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown:</p>
                  <pre class="mt-1 px-2 py-1.5 bg-background rounded text-xs"><code>1. 列表项 1
2. 列表项 2
3. 列表项 3</code></pre>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <!-- 引用和代码 -->
          <div>
            <h3 class="text-lg font-semibold mb-3">引用和代码块</h3>
            <div class="space-y-3 text-sm">
              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Quote class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">引用</p>
                  <p class="text-muted-foreground">点击工具栏的引用按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+B</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown: <code class="px-1.5 py-0.5 bg-background rounded">&gt; 引用文本</code></p>
                </div>
              </div>

              <div class="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Code class="h-5 w-5 mt-0.5 text-muted-foreground flex-shrink-0" />
                <div class="flex-1">
                  <p class="font-medium mb-1">代码块</p>
                  <p class="text-muted-foreground">点击工具栏的代码按钮，或使用快捷键 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Alt+C</kbd></p>
                  <p class="text-xs text-muted-foreground mt-2">Markdown:</p>
                  <pre class="mt-1 px-2 py-1.5 bg-background rounded text-xs"><code>```
代码内容
```</code></pre>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <!-- 数学公式 -->
          <div>
            <h3 class="text-lg font-semibold mb-3 flex items-center gap-2">
              <Sigma class="h-5 w-5" />
              数学公式
            </h3>
            <div class="space-y-3 text-sm">
              <div class="p-4 rounded-lg bg-muted/50">
                <p class="font-medium mb-2">插入 LaTeX 公式</p>
                <ol class="space-y-2 text-muted-foreground list-decimal list-inside">
                  <li>点击工具栏的 <Sigma class="inline h-4 w-4 mx-1" /> 按钮</li>
                  <li>在弹出的公式编辑器中输入 LaTeX 代码</li>
                  <li>可以使用虚拟键盘快速输入常用数学符号</li>
                  <li>实时预览公式效果</li>
                  <li>点击"插入"按钮完成</li>
                </ol>
                
                <div class="mt-4 space-y-2">
                  <p class="font-medium">常用公式示例：</p>
                  <div class="space-y-1 text-xs">
                    <div class="flex gap-4 items-center">
                      <code class="px-2 py-1 bg-background rounded flex-1">x^2 + y^2 = r^2</code>
                      <span class="text-muted-foreground">平方</span>
                    </div>
                    <div class="flex gap-4 items-center">
                      <code class="px-2 py-1 bg-background rounded flex-1">\frac{a}{b}</code>
                      <span class="text-muted-foreground">分数</span>
                    </div>
                    <div class="flex gap-4 items-center">
                      <code class="px-2 py-1 bg-background rounded flex-1">\sqrt{x}</code>
                      <span class="text-muted-foreground">根号</span>
                    </div>
                    <div class="flex gap-4 items-center">
                      <code class="px-2 py-1 bg-background rounded flex-1">\sum_{i=1}^{n} x_i</code>
                      <span class="text-muted-foreground">求和</span>
                    </div>
                    <div class="flex gap-4 items-center">
                      <code class="px-2 py-1 bg-background rounded flex-1">\int_{a}^{b} f(x)dx</code>
                      <span class="text-muted-foreground">积分</span>
                    </div>
                  </div>
                </div>

                <div class="mt-4 p-3 bg-blue-50 dark:bg-blue-950/30 rounded border border-blue-200 dark:border-blue-800">
                  <p class="text-xs text-blue-900 dark:text-blue-100">
                    💡 <strong>提示：</strong> 公式在编辑器中会以 <code class="px-1 py-0.5 bg-white dark:bg-gray-900 rounded">$公式内容$</code> 的形式保存为 Markdown。
                  </p>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <!-- 图片插入 -->
          <div>
            <h3 class="text-lg font-semibold mb-3 flex items-center gap-2">
              <ImageIcon class="h-5 w-5" />
              图片插入
            </h3>
            <div class="space-y-3 text-sm">
              <div class="p-4 rounded-lg bg-muted/50">
                <p class="font-medium mb-3">支持三种方式插入图片：</p>
                
                <!-- 方式1: 点击按钮 -->
                <div class="mb-4">
                  <div class="flex items-center gap-2 mb-2">
                    <Mouse class="h-4 w-4 text-primary" />
                    <span class="font-medium">方式一：点击按钮上传</span>
                  </div>
                  <ol class="space-y-1 text-muted-foreground list-decimal list-inside ml-6">
                    <li>点击工具栏的 <ImageIcon class="inline h-4 w-4 mx-1" /> 图片按钮</li>
                    <li>在弹出的文件选择器中选择图片</li>
                    <li>图片自动上传并插入到编辑器中</li>
                  </ol>
                </div>

                <!-- 方式2: 粘贴 -->
                <div class="mb-4">
                  <div class="flex items-center gap-2 mb-2">
                    <Keyboard class="h-4 w-4 text-primary" />
                    <span class="font-medium">方式二：粘贴图片</span>
                  </div>
                  <ol class="space-y-1 text-muted-foreground list-decimal list-inside ml-6">
                    <li>复制图片到剪贴板（截图、复制图片文件等）</li>
                    <li>在编辑器中按 <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+V</kbd> (Windows/Linux) 或 <kbd class="px-2 py-1 text-xs bg-background border rounded">Cmd+V</kbd> (Mac)</li>
                    <li>图片自动上传并插入</li>
                  </ol>
                </div>

                <!-- 方式3: 拖拽 -->
                <div class="mb-4">
                  <div class="flex items-center gap-2 mb-2">
                    <Mouse class="h-4 w-4 text-primary" />
                    <span class="font-medium">方式三：拖拽上传</span>
                  </div>
                  <ol class="space-y-1 text-muted-foreground list-decimal list-inside ml-6">
                    <li>从文件管理器中选择图片文件</li>
                    <li>拖拽到编辑器区域并释放</li>
                    <li>图片自动上传并插入到拖放位置</li>
                  </ol>
                </div>

                <div class="mt-4 p-3 bg-green-50 dark:bg-green-950/30 rounded border border-green-200 dark:border-green-800">
                  <p class="text-xs text-green-900 dark:text-green-100">
                    ✅ <strong>支持的格式：</strong> JPG, PNG, GIF, WebP 等常见图片格式
                  </p>
                </div>

                <div class="mt-2 p-3 bg-amber-50 dark:bg-amber-950/30 rounded border border-amber-200 dark:border-amber-800">
                  <p class="text-xs text-amber-900 dark:text-amber-100">
                    ⚠️ <strong>注意：</strong> 图片会自动上传到服务器，上传后以 <code class="px-1 py-0.5 bg-white dark:bg-gray-900 rounded">![](url)</code> 的 Markdown 格式保存。
                  </p>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <!-- 快捷键总览 -->
          <div>
            <h3 class="text-lg font-semibold mb-3 flex items-center gap-2">
              <Keyboard class="h-5 w-5" />
              快捷键总览
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">粗体</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+B</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">斜体</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+I</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">无序列表</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+8</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">有序列表</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+7</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">引用</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Shift+B</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">代码块</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Alt+C</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">粘贴图片</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+V</kbd>
                </div>
              </div>
              <div class="p-3 rounded-lg bg-muted/50">
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">撤销</span>
                  <kbd class="px-2 py-1 text-xs bg-background border rounded">Ctrl+Z</kbd>
                </div>
              </div>
            </div>
            <p class="text-xs text-muted-foreground mt-3">
              * Mac 用户请将 Ctrl 替换为 Cmd
            </p>
          </div>
        </CardContent>
      </Card>

      <!-- 底部提示 -->
      <div class="p-4 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 text-sm">
        <p class="text-blue-900 dark:text-blue-100">
          📚 更多功能正在开发中，敬请期待！如有问题或建议，请联系系统管理员。
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
kbd {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  overflow-x: auto;
}
</style>
