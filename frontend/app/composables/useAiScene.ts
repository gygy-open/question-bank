// Current page scene for the global AI assistant.
// Module-scoped singleton (same pattern as useGlobalChat) so the value survives
// route changes and is readable from the chat stream, which lives outside any
// component instance.
//
// The scene only narrows which tools the model is offered and adds one line of
// context to the system prompt. It is client-reported and therefore untrusted —
// it must never be used for authorization. Real gating lives in the capability
// layer on the server.

// Vue imports are explicit (not Nuxt auto-imports) so this is unit-testable.
import { ref, readonly, onActivated, onDeactivated, onMounted, onUnmounted, watchEffect } from 'vue'

export type AiScene = 'question_library' | 'composition_editor' | 'import_review'

export interface AiSceneContext {
    [key: string]: string | number | boolean | null | undefined
}

const scene = ref<AiScene | null>(null)
const context = ref<AiSceneContext | null>(null)

export function useAiScene() {
    const setScene = (next: AiScene, ctx?: AiSceneContext) => {
        scene.value = next
        context.value = ctx ?? null
    }

    const setContext = (ctx: AiSceneContext) => {
        context.value = ctx
    }

    const clearScene = () => {
        scene.value = null
        context.value = null
    }

    /**
     * Declare the scene for as long as the calling page is the one on screen.
     *
     * onMounted/onUnmounted alone is not enough: app.vue uses a global
     * <NuxtPage keepalive />, so a page the user navigated away from stays mounted and
     * would keep claiming the scene — offering the model tools for a page nobody is on.
     */
    const useSceneWhileMounted = (next: AiScene, ctx?: () => AiSceneContext) => {
        const claim = () => setScene(next, ctx?.())
        const release = () => {
            if (scene.value === next) clearScene()
        }
        onMounted(claim)
        if (ctx) {
            watchEffect(() => {
                if (scene.value === next) context.value = ctx()
            })
        }
        // onActivated also fires on the initial mount; setScene is idempotent.
        onActivated(claim)
        onDeactivated(release)
        onUnmounted(release)
    }

    return {
        scene: readonly(scene),
        context: readonly(context),
        setScene,
        setContext,
        clearScene,
        useSceneWhileMounted,
    }
}
