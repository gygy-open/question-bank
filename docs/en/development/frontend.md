# Frontend Conventions

The frontend is Nuxt 4 (SPA) + Vue 3.5 + TypeScript + Tailwind v4 + Shadcn UI.

## SPA Mode

`nuxt.config.ts` sets `ssr: false`, so the app runs with client-side rendering only.

## Components

Use `<script setup lang="ts">`:

```vue
<script setup lang="ts">
const count = ref(0)
</script>
```

## State

Prefer `ref` over `reactive`.

## API Calls

Always go through the `useAPI` composable:

```ts
const { data } = await useAPI('/endpoint')
```

Auth headers are injected automatically by `app/plugins/api.ts`; you don't need to handle them yourself.

## Form Validation

Use `zod` schemas + `vee-validate`.

## Styling

- Prefer Tailwind v4 utility classes and avoid scoped CSS where possible.
- Use `lucide-vue-next` for all icons.
- UI components live in `app/components/ui/` (Shadcn style).

## Rich Text and Math

- Editing: `tiptap`
- Rendering: `katex`
- Formula input: `mathlive`

## Internationalization

Don't hardcode UI text. Always use `t()` with keys from `frontend/i18n/locales/zh-CN.json`; translations are maintained with the `pnpm i18n:*` scripts (see the i18n section of `.github/copilot-instructions.md` for the workflow).

## Path Alias

Use `@/` to refer to the frontend `app/` root.

## Directory Overview

| Directory | Responsibility |
|------|------|
| `app/pages/` | Page routes |
| `app/components/` | Components (`ui/` holds base components) |
| `app/composables/` | Composables (e.g. `useAPI`) |
| `app/plugins/` | Plugins (e.g. `api.ts`) |
| `app/layouts/` | Layouts |
