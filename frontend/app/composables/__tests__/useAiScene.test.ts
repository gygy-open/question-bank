import { describe, it, expect, beforeEach } from 'vitest'
import { useAiScene } from '../useAiScene'

describe('useAiScene', () => {
    beforeEach(() => {
        useAiScene().clearScene()
    })

    it('reports no scene by default so the server exposes every tool', () => {
        const { scene, context } = useAiScene()
        expect(scene.value).toBeNull()
        expect(context.value).toBeNull()
    })

    it('is a module-scoped singleton shared across call sites', () => {
        useAiScene().setScene('composition_editor', { composition_id: 42 })
        // A separate call site must observe the same state — the chat stream lives
        // outside the component that declared the scene.
        const other = useAiScene()
        expect(other.scene.value).toBe('composition_editor')
        expect(other.context.value).toEqual({ composition_id: 42 })
    })

    it('clears both scene and context', () => {
        useAiScene().setScene('question_library', { a: 1 })
        useAiScene().clearScene()
        expect(useAiScene().scene.value).toBeNull()
        expect(useAiScene().context.value).toBeNull()
    })

    it('replaces context without changing scene', () => {
        const { setScene, setContext, scene, context } = useAiScene()
        setScene('composition_editor', { revision: 1 })
        setContext({ revision: 2 })
        expect(scene.value).toBe('composition_editor')
        expect(context.value).toEqual({ revision: 2 })
    })
})
