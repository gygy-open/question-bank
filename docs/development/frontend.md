# 前端约定

前端为 Nuxt 4(SPA)+ Vue 3.5 + TypeScript + Tailwind v4 + Shadcn UI。

## SPA 模式

`nuxt.config.ts` 中 `ssr: false`，以纯客户端渲染运行。

## 组件

使用 `<script setup lang="ts">`：

```vue
<script setup lang="ts">
const count = ref(0)
</script>
```

## 状态

优先使用 `ref` 而非 `reactive`。

## API 调用

统一走 `useAPI` composable:

```ts
const { data } = await useAPI('/endpoint')
```

鉴权头由 `app/plugins/api.ts` 自动注入，无需手动处理。

## 表单校验

使用 `zod` schema + `vee-validate`。

## 样式

- Tailwind v4 utility class 优先，尽量避免 scoped CSS。
- 图标统一使用 `lucide-vue-next`。
- UI 组件位于 `app/components/ui/`（Shadcn 风格）。

## 富文本与数学

- 编辑：`tiptap`
- 渲染：`katex`
- 公式输入：`mathlive`

## 路径别名

使用 `@/` 指向前端 `app/` 根目录。

## 目录速览

| 目录 | 职责 |
|------|------|
| `app/pages/` | 页面路由 |
| `app/components/` | 组件（`ui/` 为基础组件） |
| `app/composables/` | 组合式函数（如 `useAPI`） |
| `app/plugins/` | 插件（如 `api.ts`） |
| `app/layouts/` | 布局 |
