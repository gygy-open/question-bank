import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

export default defineConfig({
    test: {
        environment: 'happy-dom',
        include: ['app/**/*.{test,spec}.ts'],
    },
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./app', import.meta.url)),
        },
    },
})
