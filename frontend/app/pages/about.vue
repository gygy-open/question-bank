<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import PageHeader from '~/components/PageHeader.vue'
import { Download, RefreshCw, Bug, ExternalLink, Heart, Package } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { onMounted, ref, computed } from 'vue'

definePageMeta({
  layout: 'default',
})

const { user } = useAuth()
const isSuperuser = computed(() => !!user.value?.is_superuser)

const { state: updateState, check: checkUpdate } = useUpdateCheck()
const localVersion = ref<string>('-')

const REPO_URL = 'https://github.com/gygy-open/question-bank'
const ISSUE_URL = `${REPO_URL}/issues/new`

// 手动维护的共创者名单：名字 + 一句致敬描述
const contributors: { name: string; note: string; url?: string }[] = [
  { name: 'Xuemei Wang', note: '没有她就没有这个项目' },
  { name: '寻梦', note: '他以优质的反馈和建议鞭策项目不断完善' },
]

// 精选的核心开源依赖（完整清单见 package.json / pyproject.toml）
const ossCredits: { name: string; license: string; url: string }[] = [
  { name: 'Nuxt', license: 'MIT', url: 'https://nuxt.com' },
  { name: 'Vue', license: 'MIT', url: 'https://vuejs.org' },
  { name: 'Reka UI', license: 'MIT', url: 'https://reka-ui.com' },
  { name: 'Tailwind CSS', license: 'MIT', url: 'https://tailwindcss.com' },
  { name: 'shadcn-vue', license: 'MIT', url: 'https://www.shadcn-vue.com' },
  { name: 'Tiptap', license: 'MIT', url: 'https://tiptap.dev' },
  { name: 'KaTeX', license: 'MIT', url: 'https://katex.org' },
  { name: 'MathLive', license: 'MIT', url: 'https://mathlive.io' },
  { name: 'Lucide', license: 'ISC', url: 'https://lucide.dev' },
  { name: 'FastAPI', license: 'MIT', url: 'https://fastapi.tiangolo.com' },
  { name: 'SQLAlchemy', license: 'MIT', url: 'https://www.sqlalchemy.org' },
  { name: 'Alembic', license: 'MIT', url: 'https://alembic.sqlalchemy.org' },
  { name: 'Pydantic', license: 'MIT', url: 'https://pydantic.dev' },
  { name: 'ChromaDB', license: 'Apache-2.0', url: 'https://www.trychroma.com' },
  { name: 'Pandoc', license: 'GPL-2.0+', url: 'https://pandoc.org' },
  { name: 'pandas', license: 'BSD-3-Clause', url: 'https://pandas.pydata.org' },
  { name: 'Uvicorn', license: 'BSD-3-Clause', url: 'https://www.uvicorn.org' },
  { name: 'Pillow', license: 'HPND', url: 'https://python-pillow.org' },
  { name: 'pystray', license: 'LGPL-3.0', url: 'https://github.com/moses-palmer/pystray' },
]

const handleCheckUpdate = async () => {
  await checkUpdate(true)
  if (updateState.value.error) {
    toast.error('检查更新失败', { description: updateState.value.error })
  } else if (updateState.value.hasUpdate) {
    window.open(updateState.value.releaseUrl, '_blank')
  } else {
    toast.success('已是最新版本', { description: `当前版本 v${updateState.value.current}` })
  }
}

onMounted(async () => {
  // 不论是否是管理员，都检查版本，以便界面上能提示是否发现了“最新版本”
  await checkUpdate()
  localVersion.value = updateState.value.current || '-'
})
</script>

<template>
  <!-- 环境背景设计：进一步弱化光晕，让它变成非常非常微弱的氛围光 -->
  <div class="pointer-events-none absolute inset-x-0 top-0 z-0 h-[800px] overflow-hidden">
    <div class="absolute inset-0 bg-[linear-gradient(to_right,#e5e7eb_1px,transparent_1px),linear-gradient(to_bottom,#e5e7eb_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#27272a_1px,transparent_1px),linear-gradient(to_bottom,#27272a_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_60%_80%_at_50%_0%,#000_80%,transparent_100%)]"></div>
    <!-- 调低不透明度，减小高度，避免抢戏。改为主题色 #2F7A6B 对应的 Tailwind 绿/蓝绿色系（使用 primary/teal 变体）以保证风格统一 -->
    <div class="absolute top-0 left-1/2 h-[300px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/15 blur-[100px] dark:bg-primary/20"></div>
  </div>

  <PageHeader title="关于" class="relative z-10" />

  <div class="relative z-10 mx-auto w-full max-w-3xl space-y-10 p-4 sm:p-6 lg:p-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
    <!-- Hero 区域：增加微小的间距调整和副标题变淡，突出按钮层次 -->
    <section class="flex flex-col items-center gap-4 py-8 text-center">
      <div class="relative shadow-sm rounded-2xl bg-white dark:bg-zinc-900 p-3 ring-1 ring-zinc-200 dark:ring-zinc-800">
        <img src="/logo.svg" alt="题库系统" class="size-14" />
      </div>
      <div class="space-y-2 mt-2">
        <h1 class="text-3xl font-extrabold tracking-tight bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">
            Question Bank 题库系统
        </h1>
        <p class="text-muted-foreground/80 max-w-md text-base leading-relaxed mx-auto">
          AI 原生的题库系统
        </p>
      </div>
      <p class="text-muted-foreground text-sm font-medium bg-secondary/40 px-3 py-1 rounded-full">
        当前版本 v{{ localVersion }}
      </p>
      <div class="flex flex-wrap items-center justify-center gap-3 pt-4">
        <Button v-if="isSuperuser" variant="default" class="rounded-full px-6 shadow-md" @click="handleCheckUpdate">
          <Download v-if="updateState.hasUpdate" class="mr-2 h-4 w-4" />
          <RefreshCw v-else class="mr-2 h-4 w-4" :class="updateState.checking ? 'animate-spin' : ''" />
          {{ updateState.hasUpdate ? `下载新版本 v${updateState.latest}` : '检查更新' }}
        </Button>
        <Button v-else variant="secondary" disabled class="rounded-full px-6 opacity-80">
          <Download v-if="updateState.hasUpdate" class="mr-2 h-4 w-4" />
          <RefreshCw v-else class="mr-2 h-4 w-4" :class="updateState.checking ? 'animate-spin' : ''" />
          {{ updateState.hasUpdate ? `发现新版 v${updateState.latest} · 请联系管理员更新` : (updateState.checking ? '检查版本中...' : '已是最新版本') }}
        </Button>
        <Button variant="outline" class="rounded-full px-5" as-child>
          <a :href="ISSUE_URL" target="_blank" rel="noopener noreferrer">
            <Bug class="mr-2 h-4 w-4 text-orange-500" /> 反馈问题
          </a>
        </Button>
        <Button variant="ghost" class="rounded-full px-5" as-child>
          <a :href="REPO_URL" target="_blank" rel="noopener noreferrer">
            <ExternalLink class="mr-2 h-4 w-4" /> GitHub
          </a>
        </Button>
      </div>
    </section>

    <!-- 共创者区域：情感化设计的核心体现 -->
    <section class="mt-8">
      <!-- 鸣谢标题改为居中对齐，维持和顶部 Hero 的中轴对称 -->
      <div class="flex flex-col items-center justify-center gap-1 mb-8 text-center">
        <Heart class="h-6 w-6 text-primary/80 mb-1 fill-primary/10 dark:fill-primary/20" />
        <h2 class="text-xl font-bold tracking-tight">特别鸣谢</h2>
        <p class="text-sm text-muted-foreground">感谢陪伴本项目成长并默默付出的每一位朋友</p>
      </div>
      
      <div class="grid gap-4 sm:grid-cols-2">
        <div 
          v-for="c in contributors" 
          :key="c.name"
          class="group relative flex flex-col justify-center items-center overflow-hidden rounded-[20px] bg-background/50 border border-border/50 p-6 text-center transition-all hover:bg-card hover:border-primary/20 hover:shadow-[0_8px_30px_rgb(47,122,107,0.06)] dark:hover:border-primary/40"
        >
          <!-- 卡片内部悬浮光晕（极光效果，采用系统主题色与辅助淡蓝交织） -->
          <div class="absolute -bottom-8 -right-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl transition-transform duration-700 group-hover:scale-150 group-hover:bg-primary/15 dark:bg-primary/20"></div>
          <div class="absolute -top-8 -left-8 h-24 w-24 rounded-full bg-sky-400/5 blur-2xl transition-transform duration-700 group-hover:scale-150"></div>

          <div class="relative z-10 flex flex-col items-center">
            <a 
              v-if="c.url" 
              :href="c.url" 
              target="_blank" 
              rel="noopener noreferrer" 
              class="font-semibold text-base mb-3 hover:text-primary dark:hover:text-primary transition-colors"
            >
              <span class="text-primary/70 mr-[2px] font-normal">@</span>{{ c.name }}
            </a>
            <span v-else class="font-semibold text-base mb-3">
              <span class="text-primary/70 mr-[2px] font-normal">@</span>{{ c.name }}
            </span>
            
            <p class="text-sm text-muted-foreground/80 leading-relaxed font-medium">
              {{ c.note }}
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- 开源许可区域保持原来的简约云标签不变 -->
    <section class="rounded-[20px] border border-border/50 bg-background/50 p-6 mt-8">
      <div class="flex items-center justify-center gap-2 mb-6">
        <Package class="h-4 w-4 text-muted-foreground" />
        <h2 class="font-semibold">开源基石</h2>
      </div>
      <div class="flex flex-wrap justify-center gap-2.5">
        <a
          v-for="lib in ossCredits"
          :key="lib.name"
          :href="lib.url"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-2 rounded-full border bg-secondary/30 px-3 py-1.5 text-xs font-medium text-foreground transition-all hover:bg-secondary hover:-translate-y-0.5 hover:shadow-sm"
        >
          {{ lib.name }}
          <span class="text-[10px] text-muted-foreground font-normal border-l pl-2">{{ lib.license }}</span>
        </a>
      </div>
      <p class="mt-8 text-[11px] text-muted-foreground/60 flex items-center justify-center border-t pt-4">
        本项目以 AGPL-3.0 许可开源，感谢开源社区的无私贡献。
      </p>
    </section>
  </div>
</template>
