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
import { ref, readonly, onMounted, onUnmounted, watchEffect } from 'vue'

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

    /** Declare the scene for as long as the calling component is mounted. */
    const useSceneWhileMounted = (next: AiScene, ctx?: () => AiSceneContext) => {
        onMounted(() => setScene(next, ctx?.()))
        if (ctx) {
            watchEffect(() => {
                if (scene.value === next) context.value = ctx()
            })
        }
        onUnmounted(clearScene)
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
